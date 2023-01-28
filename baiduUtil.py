import requests
from helperType import pathType, itemType
from driveInterface import *
import urllib3
import re
import json
from retrying import retry

BAIDU_API_BASE = "https://pan.baidu.com/api/"

REQUEST_HEADER = {
    "Host": "pan.baidu.com",
    "Connection": "keep-alive",
    "User-Agent": "netdisk;2.2.51.6;netdisk;10.0.63;PC;android-android;QTP/1.0.32.2",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "navigate",
    "Referer": "https://pan.baidu.com",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7,en-GB;q=0.6,ru;q=0.5",
}


class RetryLater(driveError):
    code: int
    message: str
    data: dict

    def __init__(self):
        self.code = 111
        self.message = "Retry Later."
        self.data = {}


class Pan(driveInterface):
    session: requests.Session
    request_header: dict
    bdstoken: str

    def __init__(self, base_path: pathType, cookies: str):
        urllib3.disable_warnings()
        self.session = requests.session()
        self.session.trust_env = False
        self.base_path = base_path
        self.drive_type = "baidunetdisk"
        self.request_header = REQUEST_HEADER
        self.request_header["Cookie"] = cookies
        self.bdstoken = ""

    def item_to_itemType(self, item: dict, **kwargs) -> itemType:
        type = item["isdir"]
        data = {
            "id": item["fs_id"] if "fs_id" in item else "-1",
            "md5": item["md5"] if "md5" in item else "",
            "size": item["size"] if "size" in item else "",
            "md5_s": "",
            "drive_type": "baidunetdisk",
        }
        if "path" in kwargs:
            path = self.base_path + kwargs["path"]
        else:
            path = self.base_path + pathType.path_from_str(item["path"], absolute=False)
        res_item = itemType(path, type, data)
        return res_item

    def get_bdstoken(self) -> str:
        payload = {
            "clienttype": 0,
            "app_id": 250528,
            "web": 1,
            "fields": '["bdstoken", "token", "uk", "isdocuser", "servertime"]',
        }
        response = self.session.get(
            url=BAIDU_API_BASE + "gettemplatevariable",
            headers=self.request_header,
            timeout=20,
            allow_redirects=True,
            verify=False,
            params=payload,
        )
        res = response.json()
        if res["errno"] != 0:
            raise driveError(res["errno"], res["errmsg"] if "errmsg" in res else "")
        self.bdstoken = res["result"]["bdstoken"]
        return res["result"]["bdstoken"]

    def get_dir_list(self, path: str) -> list:
        payload = {
            "order": "time",
            "desc": 1,
            "showempty": 0,
            "web": 1,
            "page": 1,
            "num": 1000,
            "dir": path,
            "bdstoken": self.bdstoken or self.get_bdstoken(),
        }
        response = self.session.get(
            url=BAIDU_API_BASE + "list",
            headers=self.request_header,
            timeout=15,
            allow_redirects=False,
            verify=False,
            params=payload,
        )
        res = response.json()
        if res["errno"] != 0:
            if res["errno"] == -9:
                raise pathNotFoundError(
                    self.get_absolute_path(
                        pathType.path_from_str(path["path"].strip("/"))
                    )
                )
            else:
                raise driveError(res["errno"], res["errmsg"] if "errmsg" in res else "")
        return res["list"]

    def rapid_upload(self, path: str, file_data: dict) -> None:
        payload = {"bdstoken": self.bdstoken or self.get_bdstoken()}
        post_data = {
            "path": path,
            "content-md5": file_data["md5"],
            "slice-md5": file_data["md5_s"],
            "content-length": file_data["size"],
        }
        response = self.session.post(
            url=BAIDU_API_BASE + "rapidupload",
            headers=self.request_header,
            data=post_data,
            timeout=15,
            allow_redirects=False,
            verify=False,
            params=payload,
        )
        if response.json()["errno"] == 404:
            post_data = {
                "path": path,
                "content-md5": file_data["md5"].lower(),
                "slice-md5": file_data["md5_s"].lower(),
                "content-length": file_data["size"],
            }
            response = self.session.post(
                url=BAIDU_API_BASE + "rapidupload",
                headers=self.request_header,
                data=post_data,
                timeout=15,
                allow_redirects=False,
                verify=False,
                params=payload,
            )
        res = response.json()
        if res["errno"] != 0:
            raise driveError(res["errno"], res["errmsg"] if "errmsg" in res else "")

    def create_dir(self, path: str) -> None:
        url = BAIDU_API_BASE + "create"
        payload = {"a": "commit", "bdstoken": self.bdstoken or self.get_bdstoken()}
        post_data = {
            "path": path,
            "isdir": "1",
            "block_list": "[]",
        }
        response = self.session.post(
            url=url,
            headers=self.request_header,
            data=post_data,
            timeout=15,
            allow_redirects=False,
            verify=False,
            params=payload,
        )
        res = response.json()
        if res["errno"] != 0:
            raise driveError(res["errno"], res["errmsg"] if "errmsg" in res else "")

    def search_file(self, dir: str, key: str, page: int = 1) -> list[itemType]:
        url = BAIDU_API_BASE + "search"
        payload = {
            "clienttype": 0,
            "app_id": 250528,
            "web": 1,
            "key": key,
            "dir": dir,
            "page": page,
            "recursion": 1,
            "bdstoken": self.bdstoken or self.get_bdstoken(),
        }
        response = self.session.get(
            url=url,
            headers=self.request_header,
            timeout=15,
            allow_redirects=False,
            verify=False,
            params=payload,
        )
        res = response.json()
        if res["errno"] != 0:
            raise driveError(res["errno"], res["errmsg"] if "errmsg" in res else "")
        res_list = []
        for item in res["list"]:
            res_list.append(self.item_to_itemType(item))
        if res["has_more"] == 1:
            res_list.extend(self.search_file(dir=dir, key=key, page=page + 1))
        return res_list

    @retry(
        wait_fixed=1000,
        stop_max_attempt_number=3,
        retry_on_exception=lambda e: e.code == 111,
    )
    def file_manager(self, opera: str, filelist) -> None:
        url = BAIDU_API_BASE + "filemanager"
        payload = {
            "async": 0,
            "onnest": "fail",
            "opera": opera,
            "clienttype": 0,
            "app_id": 250528,
            "web": 1,
            "bdstoken": self.bdstoken or self.get_bdstoken(),
        }
        post_data = {"filelist": json.dumps(filelist, ensure_ascii=False)}
        response = self.session.post(
            url=url,
            headers=self.request_header,
            data=post_data,
            timeout=15,
            allow_redirects=False,
            verify=False,
            params=payload,
        )
        res = response.json()
        if res["errno"] == 12:
            for i in range(len(res["info"])):
                if res["info"][i]["errno"] == -9:
                    raise pathNotFoundError(
                        self.get_absolute_path(
                            pathType.path_from_str(res["info"][i]["path"].strip("/"))
                        )
                    )
                elif res["info"][i]["errno"] == -8:
                    raise driveError(
                        603,
                        "Path already exists",
                        data={
                            "path": self.get_absolute_path(
                                pathType.path_from_str(filelist[i]["dest"].strip("/"))
                                + pathType([filelist[i]["newname"]], False)
                            )
                        },
                    )
                elif res["info"][i]["errno"] == 111:
                    raise RetryLater()
                else:
                    raise driveError(
                        res["errno"],
                        res["errmsg"] if "errmsg" in res else "",
                        data={"res": res},
                    )
        elif res["errno"] != 0:
            raise driveError(
                res["errno"],
                res["errmsg"] if "errmsg" in res else "",
                data={"res": res},
            )

    # 实现driveInterface接口方法
    def list_dir(self, path: pathType) -> list[itemType]:
        r_path = self.get_relative_path(path)
        res_list = []
        items = self.get_dir_list("/" + str(r_path))
        for item in items:
            res_list.append(self.item_to_itemType(item))
        return res_list

    def get_item(self, path: pathType) -> itemType:
        if path == self.base_path:
            return itemType(path, 1, data={})
        items = self.list_dir(path.dirname)
        for item in items:
            if item.path.basename == path.basename:
                return item
        raise pathNotFoundError(path)

    def search_items(self, **kwargs) -> list[itemType]:
        import sys

        if "name" not in kwargs:
            sys.stdout.write(
                "baiduUtil : -name not specified. Search files in Baidu Netdisk without parameter '-name' is not supported.\n"
            )
            return []
        sys.stdout.write(
            "baiduUtil : Search files in Baidu Netdisk will ignore wildcards and return items with specific name.\n"
        )
        dir_list = []
        res_list = []
        if "path" in kwargs and kwargs["path"]:
            if type(kwargs["path"]) == type([]):
                for path in kwargs["path"]:
                    dir_list.append(self.get_relative_path(path))
            else:
                dir_list.append(self.get_relative_path(kwargs["path"]))
        else:
            dir_list.append(pathType.path_from_str(""))
        for dir in dir_list:
            name_without_wildcards = (
                re.sub(r"\[.*?\]", "", kwargs["name"]).replace("*", "").replace("?", "")
            )
            items = self.search_file("/" + str(dir), name_without_wildcards)
            for item in items:
                if "type" in kwargs and item.type != kwargs["type"]:
                    continue
                if "max_size" in kwargs and item.data["size"] > kwargs["max_size"]:
                    continue
                if "min_size" in kwargs and item.data["size"] < kwargs["min_size"]:
                    continue
                res_list.append(item)
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
            else:
                raise driveError(603, "Path already exists", data={"path": dst_path})
        except pathNotFoundError:
            if len(src_path_list) > 1:
                raise pathNotFoundError(dst_path)
        r_dst_path = self.get_relative_path(dst_path)
        filelist = []
        for src_path in src_path_list:
            r_src_path = self.get_relative_path(src_path)
            filelist.append(
                {
                    "path": "/" + str(r_src_path),
                    "dest": "/" + str(r_dst_path if flag else r_dst_path.dirname),
                    "newname": r_src_path.basename if flag else r_dst_path.basename,
                }
            )
        self.file_manager("move", filelist)

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
            src_item = self.get_item(src_path)
            if src_item.type == 1 and not (
                "recursive" in kwargs and kwargs["recursive"]
            ):
                raise driveError(602, "Is a directory", data={"path": src_path})
            r_dst_path = self.get_relative_path(dst_path)
            filelist = []
            for src_path in src_path_list:
                r_src_path = self.get_relative_path(src_path)
                filelist.append(
                    {
                        "path": "/" + str(r_src_path),
                        "dest": "/" + str(r_dst_path if flag else r_dst_path.dirname),
                        "newname": r_src_path.basename if flag else r_dst_path.basename,
                    }
                )
            try:
                self.file_manager("copy", filelist)
            except driveError as e:
                if e.code == 603 and "force" in kwargs and kwargs["force"]:
                    self.remove_item(dst_path)
                    self.file_manager("copy", filelist)
                else:
                    raise e

    def remove_item(self, path: pathType, **kwargs) -> None:
        path_list = self.parse_wildcard(path)
        filelist = []
        for path in path_list:
            try:
                item = self.get_item(path)
            except pathNotFoundError as e:
                if "force" in kwargs and kwargs["force"]:
                    return
                else:
                    raise e
            if item.type == 1 and not ("recursive" in kwargs and kwargs["recursive"]):
                raise driveError(602, "Is a directory", data={"path": path})
            r_path = self.get_relative_path(path)
            filelist.append("/" + str(r_path))
        self.file_manager("delete", filelist)

    def add_item(self, path: pathType, type: int, **kwargs) -> None:
        r_path = self.get_relative_path(path)
        if type == 0:
            data = {
                "size": kwargs["size"],
                "md5": kwargs["md5"],
                "md5_s": kwargs["md5_s"],
            }
            self.rapid_upload("/" + str(r_path), data)
        else:
            self.create_dir("/" + str(r_path))
