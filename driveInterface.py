from helperType import pathType, itemType
from fnmatch import fnmatch


class driveError(Exception):
    code: int
    message: str
    data: dict

    def __init__(self, code: int, message: str = "", data: dict = {}) -> None:
        self.code = code
        self.message = message
        self.data = data


class pathNotFoundError(driveError):
    code: int
    message: str
    data: dict

    def __init__(self, path: pathType):
        self.code = 404
        self.message = "Path Not Found."
        self.data = {"path": path}


class driveInterface:
    base_path: pathType
    drive_type: str

    def __init__(self, base_path: pathType, *args):
        base_path = base_path

    def __contains__(self, path: pathType) -> bool:
        return path in self.base_path

    def __eq__(self, other) -> bool:
        return self.base_path == other.base_path

    def __hash__(self) -> int:
        return hash(self.base_path)

    def parse_wildcard(self, path: pathType) -> list[pathType]:
        res_list = []
        if type(path) == type([]):
            for p in path:
                res_list.extend(self.parse_wildcard(p))
            return res_list
        else:
            for item in self.list_dir(path.dirname):
                if item.name == path.basename or fnmatch(item.name, path.basename):
                    res_list.append(item.path)
            return res_list

    def get_relative_path(self, path: pathType) -> pathType:
        if not path.absolute:
            return path
        else:
            return path - self.base_path

    def get_absolute_path(self, path: pathType) -> pathType:
        if path.absolute:
            return path
        else:
            return self.base_path + path

    def list_dir(self, path: pathType) -> list[itemType]:
        pass

    def get_item(self, path: pathType) -> itemType:
        pass

    def search_items(self, **kwargs) -> list[itemType]:
        pass

    def move_item(self, src_path: pathType, dst_path: pathType, **kwargs) -> None:
        pass

    def copy_item(self, src_path: pathType, dst_path: pathType, **kwargs) -> None:
        pass

    def remove_item(self, path: pathType, **kwargs) -> None:
        pass

    def add_item(self, path: pathType, type: int, **kwargs) -> None:
        pass


class driveUnion(driveInterface):
    drives: list[driveInterface]

    def __init__(self, base_path: pathType, *args):
        self.base_path = base_path
        self.drive_type = "union"
        self.drives = []
        for drive in args:
            self.drives.append(drive)

    def get_drive_by_path(self, path: pathType) -> driveInterface:
        for drive in self.drives:
            if path in drive:
                return drive

    def get_drives_in_path(self, path: pathType) -> list[driveInterface]:
        res_list = []
        for drive in self.drives:
            if drive.base_path in path:
                res_list.append(drive)
        return res_list

    def add_drive(self, drive: driveInterface):
        self.drives.append(drive)

    def list_dir(self, path: pathType) -> list[itemType]:
        drive = self.get_drive_by_path(path)
        if drive:
            return drive.list_dir(path)
        else:
            res_list = []
            drives = self.get_drives_in_path(path)
            for drive in drives:
                name = (drive.base_path - path)[0]
                item_path = path + pathType([name], False)
                res_list.append(itemType(path=item_path, type=1, data={}))
            return res_list

    def get_item(self, path: pathType) -> itemType:
        drive = self.get_drive_by_path(path)
        if drive and drive.base_path != path:
            return drive.get_item(path)
        else:
            drives = self.get_drives_in_path(path)
            if drives:
                return itemType(path=path, type=1, data={})
            else:
                raise pathNotFoundError(path)

    def search_items(self, **kwargs) -> list[itemType]:
        path_list = []
        if "path" in kwargs:
            if type(kwargs["path"]) == type([]):
                for path in kwargs["path"]:
                    path_list.append(path)
            else:
                path_list.append(kwargs["path"])
        else:
            for drive in self.drives:
                path_list.append(drive.base_path)
        search_list: dict[driveInterface, list[pathType]] = {}
        for path in path_list:
            drive = self.get_drive_by_path(path)
            if drive:
                if drive in search_list:
                    search_list[drive].append(path)
                else:
                    search_list[drive] = [path]
            else:
                drives = self.get_drives_in_path(path)
                for drive in drives:
                    if drive in search_list:
                        search_list[drive].append(drive.base_path)
                    else:
                        search_list[drive] = [drive.base_path]
        res_list = []
        for drive in search_list:
            search_arg = kwargs.copy()
            search_arg.update({"path": search_list[drive]})
            res_list.extend(drive.search_items(**search_arg))
        return res_list

    def move_item(self, src_path: pathType, dst_path: pathType, **kwargs) -> None:
        src_drive = self.get_drive_by_path(src_path)
        dst_drive = self.get_drive_by_path(dst_path)
        if not src_drive or not dst_drive:
            raise driveError(600, "Not in Drives")
        if src_drive == dst_drive:
            src_drive.move_item(src_path, dst_path)
        elif "cross_drive" in kwargs and kwargs["cross_drive"]:
            self.copy_item(src_path, dst_path, recursive=True, **kwargs)
            self.remove_item(src_path, recursive=True, **kwargs)
        else:
            raise driveError(
                601,
                "Not in the Same Drive",
                data={"drives": [src_drive, dst_drive]},
            )

    def copy_item(self, src_path: pathType, dst_path: pathType, **kwargs) -> None:
        src_drive = self.get_drive_by_path(src_path)
        dst_drive = self.get_drive_by_path(dst_path)
        if not src_drive or not dst_drive:
            raise driveError(600, "Not in Drives")
        if src_drive == dst_drive:
            src_drive.copy_item(src_path, dst_path, **kwargs)
        elif "cross_drive" in kwargs and kwargs["cross_drive"]:
            flag = False
            src_path_list = self.parse_wildcard(src_path)
            try:
                dst_item = self.get_item(dst_path)
                if dst_item.type == 1:
                    flag = True
                elif len(src_path_list) > 1:
                    raise driveError(604, "Not a directory", data={"path": dst_path})
                else:
                    raise driveError(
                        603, "Path already exists", data={"path": dst_path}
                    )
            except pathNotFoundError:
                if len(src_path_list) > 1:
                    raise pathNotFoundError(dst_path)
            for src_path in src_path_list:
                src_item = self.get_item(src_path)
                if src_item.type == 1 and not (
                    "recursive" in kwargs and kwargs["recursive"]
                ):
                    raise driveError(602, "Is a directory", data={"path": src_path})
                dst_drive.add_item(
                    path=(dst_path + pathType([src_item.name], False))
                    if flag
                    else dst_path,
                    type=src_item.type,
                    size=src_item.data["size"],
                    md5=src_item.data["md5"],
                    md5_s=src_item.data["md5_s"],
                )
                if src_item.type == 1:
                    items = src_drive.list_dir(src_path)
                    for item in items:
                        self.copy_item(
                            src_path + pathType([item.name], False),
                            dst_path + pathType([item.name], False),
                            **kwargs
                        )
        else:
            raise driveError(
                601,
                "Not in the Same Drive",
                data={"drives": [src_drive, dst_drive]},
            )

    def remove_item(self, path: pathType, **kwargs) -> None:
        drive = self.get_drive_by_path(path)
        if not drive:
            raise driveError(600, "Not in Drives")
        drive.remove_item(path, **kwargs)

    def add_item(self, path: pathType, type: int, **kwargs) -> None:
        drive = self.get_drive_by_path(path)
        if not drive:
            raise driveError(600, "Not in Drives")
        drive.add_item(path, type, **kwargs)
