import os
import cmd2
from baiduUtil import Pan
from dbUtil import DB
from helperType import pathType, itemType
from driveInterface import *
import json


class LibraryShell(cmd2.Cmd):
    drives: driveUnion
    now_path: pathType

    def __init__(self):
        shortcuts = cmd2.DEFAULT_SHORTCUTS
        shortcuts.update({"exit": "quit"})
        shortcuts.update({"dadd": "driveadd"})
        shortcuts.update({"drm": "driveremove"})
        super().__init__(shortcuts=shortcuts)
        self.now_path = pathType([], True)
        self.drives = driveUnion("/")
        if os.path.exists("drives.json"):
            with open("drives.json", "r", encoding="utf-8") as f:
                drives = json.load(f)
            for drive in drives:
                self.add_drive(drive)
        else:
            with open("drives.json", "w", encoding="utf-8") as f:
                f.write("[]")

    def add_drive(self, drive: dict):
        if drive["type"] == "database":
            self.drives.add_drive(
                DB(pathType.path_from_str(drive["path"]), *drive["args"])
            )
        elif drive["type"] == "baidunetdisk":
            self.drives.add_drive(
                Pan(pathType.path_from_str(drive["path"]), *drive["args"])
            )

    def get_prompt(self) -> str:
        return str(self.now_path) + " > "

    def list_items(self, items: list[itemType], one_item_per_line: bool):
        for item in items:
            name_str = str(item.path - self.now_path)
            if " " in name_str:
                name_str = "'{}'".format(name_str)
            if item.type == 1:
                name_str = "\033[34m{}\033[0m".format(name_str)
            if one_item_per_line:
                type_str = cmd2.utils.align_left(
                    "file" if item.type == 0 else "dir", width=16
                )
                size_str = cmd2.utils.align_left(
                    str(item.data["size"])
                    if "size" in item.data and item.data["size"] != 0
                    else "",
                    width=16,
                )
                self.poutput(type_str + size_str + name_str)
            else:
                self.poutput(name_str, end=" ")
        if not one_item_per_line:
            self.poutput()

    cd_parser = cmd2.Cmd2ArgumentParser()
    cd_parser.add_argument("path")

    @cmd2.with_argparser(cd_parser)
    def do_cd(self, args):
        """Change the shell working directory."""
        tmp_path = self.now_path + pathType.path_from_str(args.path)
        try:
            if self.drives.get_item(tmp_path).type != 1:
                self.perror("cd : Not a directory.")
            else:
                self.now_path = tmp_path
        except pathNotFoundError as e:
            self.perror(
                "cd : No such file or directory. {}".format(str(e.data["path"]))
            )

    ls_parser = cmd2.Cmd2ArgumentParser()
    ls_parser.add_argument(
        "-l", "-list", "--list", action="store_true", help="List one file per line"
    )
    ls_parser.add_argument(
        "path", nargs="*", help="Path to list, default to current directory"
    )

    @cmd2.with_argparser(ls_parser)
    def do_ls(self, args):
        """List information about the FILEs (the current directory by default)."""
        if not args.path:
            items = self.drives.list_dir(self.now_path)
            self.list_items(items, args.list)
        else:
            for path in args.path:
                self.poutput("{} :".format(path))
                items = self.drives.list_dir(
                    self.now_path + pathType.path_from_str(path)
                )
                self.list_items(items, args.list)

    find_parser = cmd2.Cmd2ArgumentParser()
    find_parser.add_argument("-n", "-name", "--name", help="Pattern")
    find_parser.add_argument(
        "-s", "-size", "--size", default=0, type=int, help="File size"
    )
    find_parser.add_argument(
        "-t",
        "-type",
        "--type",
        choices=["a", "d", "f"],
        help="Item Type, 'd': directory, 'f': file, 'a': all",
    )
    find_parser.add_argument(
        "path", nargs="*", help="Path to search, default to current directory."
    )

    @cmd2.with_argparser(find_parser)
    def do_find(self, args):
        """Search files or folders."""
        search_path_list = []
        if args.path:
            for path in args.path:
                search_path_list.append(self.now_path + pathType.path_from_str(path))
        else:
            search_path_list.append(self.now_path)
        search_args = {"path": search_path_list}
        if args.name:
            search_args["name"] = args.name
        if args.type:
            if args.type == "d":
                search_args["type"] = 1
            elif args.type == "f":
                search_args["type"] = 0
        if args.size:
            if args.size > 0:
                search_args["min_size"] = args.size
            elif args.size < 0:
                search_args["max_size"] = abs(args.size)
        items = self.drives.search_items(**search_args)
        self.list_items(items, True)

    cp_parser = cmd2.Cmd2ArgumentParser()
    cp_parser.add_argument("src_path", help="Source")
    cp_parser.add_argument("dst_path", help="Dest")
    cp_parser.add_argument(
        "-f",
        "-force",
        "--force",
        action="store_true",
        help="Overwrite if file already exists",
    )
    cp_parser.add_argument(
        "-r",
        "-recursive",
        "--recursive",
        action="store_true",
        help="Copy directories recursively",
    )

    @cmd2.with_argparser(cp_parser)
    def do_cp(self, args):
        """Copy SOURCE to DEST, or multiple SOURCE(s) to DIRECTORY."""
        try:
            src_path = self.now_path + pathType.path_from_str(args.src_path)
            dst_path = self.now_path + pathType.path_from_str(args.dst_path)
            self.drives.copy_item(src_path, dst_path, recursive=args.recursive)
        except driveError as e:
            if e.code == 601:
                if e.data["drives"][0].drive_type == "database":
                    self.drives.copy_item(
                        src_path, dst_path, recursive=args.recursive, cross_drive=True
                    )
                else:
                    self.perror(
                        "cp : Can not copy items from BaiduNetDisk to database."
                    )
            else:
                raise e

    mv_parser = cmd2.Cmd2ArgumentParser()
    mv_parser.add_argument("src_path", help="Source")
    mv_parser.add_argument("dst_path", help="Dest")
    mv_parser.add_argument(
        "-f",
        "-force",
        "--force",
        action="store_true",
        help="Overwrite if file already exists",
    )

    @cmd2.with_argparser(mv_parser)
    def do_mv(self, args):
        """Rename SOURCE to DEST, or move SOURCE(s) to DIRECTORY."""
        try:
            src_path = self.now_path + pathType.path_from_str(args.src_path)
            dst_path = self.now_path + pathType.path_from_str(args.dst_path)
            self.drives.move_item(src_path, dst_path)
        except driveError as e:
            if e.code == 601:
                if e.data["drives"][0].drive_type == "database":
                    self.drives.move_item(src_path, dst_path, cross_drive=True)
                elif e.data["drives"][0].drive_type == "baidunetdisk":
                    self.perror(
                        "mv : Can not move items from BaiduNetDisk to other drive."
                    )
                else:
                    raise e
            else:
                raise e

    rm_parser = cmd2.Cmd2ArgumentParser()
    rm_parser.add_argument("path", help="Path", nargs="+")
    rm_parser.add_argument(
        "-f",
        "-force",
        "--force",
        action="store_true",
        help=" Ignore nonexistent files",
    )
    rm_parser.add_argument(
        "-r",
        "-recursive",
        "--recursive",
        action="store_true",
        help="Copy directories recursively",
    )

    @cmd2.with_argparser(rm_parser)
    def do_rm(self, args):
        """Remove the FILE(s)."""
        for path in args.path:
            path = self.now_path + pathType.path_from_str(path)
            self.drives.remove_item(path, recursive=args.recursive, force=args.force)

    mkdir_parser = cmd2.Cmd2ArgumentParser()
    mkdir_parser.add_argument("path", help="Path", nargs="+")

    @cmd2.with_argparser(mkdir_parser)
    def do_mkdir(self, args):
        """Create the DIRECTORY(ies), if they do not already exist."""
        for path in args.path:
            path = self.now_path + pathType.path_from_str(path)
            self.drives.add_item(path, 1)

    clean_parser = cmd2.Cmd2ArgumentParser()
    clean_parser.add_argument("path", nargs="+", help="Path")
    clean_parser.add_argument(
        "-t",
        "-test",
        "--test",
        action="store_true",
        help="List files only, do not delete",
    )

    @cmd2.with_argparser(clean_parser)
    def do_clean(self, args):
        """If a folder is in the same directory as the compressed file with the same name, the folder will be deleted"""
        search_path_list = []
        path_list = []
        for path in args.path:
            search_path_list.append(self.now_path + pathType.path_from_str(path))
        for ext in ["*.7z", "*.zip"]:
            items = self.drives.search_items(path=search_path_list, name=ext)
            for item in items:
                if item.path.dirname not in path_list:
                    path_list.append(item.path.dirname)
        res_list = []
        for path in path_list:
            name_list = []
            items = self.drives.list_dir(path)
            for item in items:
                if item.type == 0:
                    ext = os.path.splitext(item.name)[-1]
                    name = os.path.splitext(item.name)[0]
                    if name in name_list:
                        res_list.append(item.path.dirname + pathType([name], False))
                    else:
                        name_list.append(name)
                else:
                    if item.name in name_list:
                        res_list.append(item.path)
                    else:
                        name_list.append(item.name)
        for path in res_list:
            self.poutput(path)
            if not args.test:
                self.drives.remove_item(path, recursive=True, force=True)

    add_parser = cmd2.Cmd2ArgumentParser()
    add_parser.add_argument("link", help="Rapid-upload link", nargs="+")

    @cmd2.with_argparser(add_parser)
    def do_add(self, args):
        """Add files to a drive by rapid-upload link."""
        for link in args.link:
            data = link.split("#")
            if len(data) != 4:
                self.perror("add : Invalid link.")
                return
            path = self.now_path + pathType.path_from_str(data[3])
            self.drives.add_item(path, 0, md5=data[0], md5_s=data[1], size=data[2])

    getlink_parser = cmd2.Cmd2ArgumentParser()
    getlink_parser.add_argument("path", help="Path", nargs="+")

    @cmd2.with_argparser(getlink_parser)
    def do_getlink(self, args):
        """Get rapid-upload link of the file."""
        path_list = []
        for path in args.path:
            path = self.now_path + pathType.path_from_str(path)
            path_list.extend(self.drives.parse_wildcard(path))
        for path in path_list:
            item = self.drives.get_item(path)
            if item.type != 0:
                self.perror("getlink : Is a directory : {}".format(str(path)))
                continue
            if item.data["drive_type"] != "database":
                self.perror(
                    "getlink : Can not get rapid-upload link from BaiduNetDisk."
                )
            else:
                self.poutput(
                    "#".join(
                        [
                            item.data["md5"],
                            item.data["md5_s"],
                            str(item.data["size"]),
                            item.name,
                        ]
                    )
                )

    driveadd_parser = cmd2.Cmd2ArgumentParser()
    driveadd_parser.add_argument("path", help="Base path")
    driveadd_parser.add_argument(
        "type",
        help="Drive type",
        choices=["baidunetdisk", "database"],
    )
    driveadd_parser.add_argument(
        "drive_args",
        nargs="+",
        help="Database file path (database) or cookies (BaiduNetDisk)",
    )

    @cmd2.with_argparser(driveadd_parser)
    def do_driveadd(self, args):
        """Add a drive."""
        path = self.now_path + pathType.path_from_str(args.path)
        if self.drives.get_drive_by_path(path) or self.drives.get_drives_in_path(path):
            self.perror("driveadd : Invalid path.")
            return
        drive = {"path": str(path), "type": args.type, "args": args.drive_args}
        self.add_drive(drive)
        with open("drives.json", "r", encoding="utf-8") as f:
            drives = json.load(f)
        drives.append(drive)
        with open("drives.json", "w", encoding="utf-8") as f:
            json.dump(drives, f)

    driveremove_parser = cmd2.Cmd2ArgumentParser()
    driveremove_parser.add_argument("path", help="Base path")

    @cmd2.with_argparser(driveremove_parser)
    def do_driveremove(self, args):
        """Remove a drive."""
        path = self.now_path + pathType.path_from_str(args.path)
        with open("drives.json", "r", encoding="utf-8") as f:
            drives = json.load(f)
        flag = False
        for i in range(len(drives)):
            if drives[i]["path"] == str(path):
                del drives[i]
                flag = True
        if flag:
            with open("drives.json", "w", encoding="utf-8") as f:
                json.dump(drives, f)
            self.poutput(
                "driveremove : Drive removed. Restart the program to update the changes."
            )
        else:
            self.poutput("driveremove : No drive removed.")

    prompt = property(fget=get_prompt)


if __name__ == "__main__":
    shell = LibraryShell()
    shell.cmdloop()
