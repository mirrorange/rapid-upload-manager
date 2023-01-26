import sqlalchemy
from sqlalchemy import Column, Integer, String, or_, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from helperType import pathType, itemType
from driveInterface import *


class Items(declarative_base()):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    type = Column(Integer)
    name = Column(String(256))
    id_path = Column(String(256))
    parent_id = Column(Integer)
    md5 = Column(String(32))
    md5_s = Column(String(32))
    size = Column(Integer)

    def __init__(self, type, name, parent_id, id_path, size, md5, md5_s):
        self.md5 = md5
        self.md5_s = md5_s
        self.size = size
        self.type = type
        self.name = name
        self.parent_id = parent_id
        self.id_path = id_path


class DB(driveInterface):
    def __init__(self, base_path: pathType, db_file: str):
        self.base_path = base_path
        self.drive_type = "database"
        self.sql = sqlalchemy.create_engine(f"sqlite:///{db_file}")
        self.sql.connect()
        Items.metadata.create_all(self.sql)
        self.session = sessionmaker(self.sql)()

    def item_to_itemType(self, item: Items, **kwargs) -> itemType:
        data = {
            "id": item.id,
            "md5": item.md5,
            "md5_s": item.md5_s,
            "size": item.size,
            "drive_type": "database",
        }
        if "path" in kwargs:
            path = self.base_path + kwargs["path"]
        else:
            path = self.base_path + self.id_to_path(item.id)
        res_item = itemType(path, item.type, data)
        return res_item

    def id_to_path(self, id: int) -> pathType:
        i = self.session.query(Items).filter_by(id=id).first()
        path = pathType([i.name], False)
        while i.parent_id != 0:
            i = self.session.query(Items).filter_by(id=i.parent_id).first()
            path = pathType([i.name], False) + path
        return path

    def path_to_id(self, path: pathType) -> int:
        r_path = self.get_relative_path(path)
        id = 0
        for p in r_path:
            item = self.session.query(Items).filter_by(parent_id=id, name=p).first()
            if item:
                id = item.id
            else:
                raise pathNotFoundError(path)
        return id

    def get_id_path(self, id: int) -> str:
        if id == 0:
            return "/"
        i = self.session.query(Items).filter_by(id=id).first()
        id_path = "/" + str(i.id)
        while i.parent_id != 0:
            i = self.session.query(Items).filter_by(id=i.parent_id).first()
            id_path = "/" + str(i.id) + id_path
        return id_path

    # 实现driveInterface接口方法

    def list_dir(self, path: pathType) -> list[itemType]:
        res_items = []
        id = self.path_to_id(path)
        items = (
            self.session.query(Items)
            .filter_by(parent_id=id)
            .order_by(Items.type.desc())
            .all()
        )
        for item in items:
            res_items.append(
                self.item_to_itemType(item, path=(path + pathType([item.name], False)))
            )
        return res_items

    def get_item(self, path: pathType) -> itemType:
        id = self.path_to_id(path)
        if id == 0:
            return itemType(self.base_path, 1, data={})
        item = self.session.query(Items).filter_by(id=id).first()
        res_item = self.item_to_itemType(item, path=path)
        return res_item

    def search_items(self, **kwargs) -> list[itemType]:
        query = self.session.query(Items)
        path_filter = []
        if "path" in kwargs and kwargs["path"]:
            if type(kwargs["path"]) == type([]):
                for path in kwargs["path"]:
                    path_filter.append(
                        Items.id_path.like("%/{}/%".format(str(self.path_to_id(path))))
                    )
            else:
                path_filter.append(
                    Items.id_path.like(
                        "%/{}/%".format(str(self.path_to_id((kwargs["path"]))))
                    )
                )
            query = query.filter(or_(*path_filter))
        if "name" in kwargs:
            query = query.filter(
                Items.name.like(kwargs["name"].replace("*", "%").replace("?", "_"))
            )
        if "type" in kwargs:
            query = query.filter_by(type=kwargs["type"])
        if "max_size" in kwargs:
            query = query.filter(Items.size <= kwargs["max_size"])
        if "min_size" in kwargs:
            query = query.filter(Items.size >= kwargs["min_size"])
        items = query.all()
        res_list = []
        for item in items:
            res_list.append(self.item_to_itemType(item))
        return res_list

    def move_item(self, src_path: pathType, dst_path: pathType, **kwargs) -> None:
        flag = False
        src_path_list = self.parse_wildcard(src_path)
        try:
            dst_item = self.get_item(dst_path)
            if dst_item.type == 1:
                flag = True
            elif len(src_path_list) > 1:
                raise driveError(604, "Not a directory", data={"path": dst_path})
            elif "force" in kwargs and kwargs["force"]:
                self.remove_item(dst_path)
            else:
                raise driveError(603, "Path already exists", data={"path": dst_path})
        except pathNotFoundError:
            if len(src_path_list) > 1:
                raise pathNotFoundError(dst_path)
        for src_path in src_path_list:
            src_id = self.path_to_id(src_path)
            src_item = self.session.query(Items).filter_by(id=src_id).first()
            parent_id = self.path_to_id(dst_path if flag else dst_path.dirname)
            self.session.query(Items).filter_by(id=src_id).update(
                {
                    Items.parent_id: parent_id,
                    Items.name: src_path.basename if flag else dst_path.basename,
                    Items.id_path: func.replace(
                        Items.id_path,
                        "/{}/".format(src_item.parent_id),
                        "/{}/".format(parent_id),
                    ),
                }
            )
            if src_item.type == 1:
                self.session.query(Items).filter(
                    Items.id_path.like("%/{}/%".format(src_id))
                ).update(
                    {
                        Items.id_path: func.replace(
                            Items.id_path,
                            "/{}/".format(src_item.parent_id),
                            "/{}/".format(parent_id),
                        )
                    },
                    synchronize_session="fetch",
                )
        self.session.commit()

    def copy_item(self, src_path: pathType, dst_path: pathType, **kwargs) -> None:
        flag = False
        src_path_list = self.parse_wildcard(src_path)
        try:
            dst_item = self.get_item(dst_path)
            if dst_item.type == 1:
                flag = True
            elif len(src_path_list) > 1:
                raise driveError(604, "Not a directory", data={"path": dst_path})
            else:
                raise driveError(603, "Path already exists", data={"path": dst_path})
        except pathNotFoundError:
            if len(src_path_list) > 1:
                raise pathNotFoundError(dst_path)
        for src_path in src_path_list:
            src_id = self.path_to_id(src_path)
            src_item = self.session.query(Items).filter_by(id=src_id).first()
            if src_item.type == 1 and not (
                "recursive" in kwargs and kwargs["recursive"]
            ):
                raise driveError(602, "Is a directory", data={"path": src_path})
            self.add_item(
                path=dst_path + pathType([src_item.name], False) if flag else dst_path,
                type=src_item.type,
                size=src_item.size,
                md5=src_item.md5,
                md5_s=src_item.md5_s,
                force=kwargs["force"] if "force" in kwargs else False,
            )
            if src_item.type == 1:
                items = self.list_dir(src_path)
                for item in items:
                    self.copy_item(
                        src_path + pathType([item.name], False),
                        dst_path + pathType([item.name], False),
                        **kwargs,
                    )

    def remove_item(self, path: pathType, **kwargs) -> None:
        path_list = self.parse_wildcard(path)
        if len(path_list) == 0 and not ("force" in kwargs and kwargs["force"]):
            raise pathNotFoundError(path)
        for path in path_list:
            id = self.path_to_id(path)
            item = self.session.query(Items).filter_by(id=id).first()
            if item.type == 1:
                if "recursive" in kwargs and kwargs["recursive"]:
                    self.session.query(Items).filter(
                        Items.id_path.like("%/{}/%".format(id))
                    ).delete(synchronize_session="fetch")
                else:
                    raise driveError(602, "Is a directory", data={"path": path})
            self.session.query(Items).filter_by(id=id).delete()
        self.session.commit()

    def add_item(self, path: pathType, type: int, **kwargs) -> None:
        try:
            id = self.path_to_id(path)
            item = self.session.query(Items).filter_by(id=id).first()
            if item.type == type and "force" in kwargs and kwargs["force"]:
                item = (
                    self.session.query(Items)
                    .filter_by(id=id)
                    .update(
                        {
                            Items.type: type,
                            Items.size: kwargs["size"] if "size" in kwargs else 0,
                            Items.md5: kwargs["md5"] if "md5" in kwargs else "",
                            Items.md5_s: kwargs["md5_s"] if "md5_s" in kwargs else "",
                        }
                    )
                )
            else:
                raise driveError(603, "Path already exists", data={"path": path})
        except pathNotFoundError:
            try:
                parent_id = self.path_to_id(path.dirname)
            except pathNotFoundError:
                self.add_item(path.dirname, 1)
                parent_id = self.path_to_id(path.dirname)
            item = Items(
                type=type,
                name=path.basename,
                parent_id=parent_id,
                size=kwargs["size"] if "size" in kwargs else 0,
                md5=kwargs["md5"] if "md5" in kwargs else "",
                md5_s=kwargs["md5_s"] if "md5_s" in kwargs else "",
                id_path="",
            )
            parent_id_path = self.get_id_path(parent_id)
            item.id_path = parent_id_path.rstrip("/") + "/" + str(item.id)
            self.session.add(item)
            self.session.commit()
