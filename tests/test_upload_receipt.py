import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from modules import upload


def test_split_receipt_files_identifies_unsigned_filelist():
    files = [
        "backup.tar",
        "backup.json",
        "backup.lst",
    ]

    payload, receipt = upload.split_receipt_files(files, "backup")

    assert payload == ["backup.tar", "backup.json"]
    assert receipt == "backup.lst"


def test_split_receipt_files_identifies_signed_filelist():
    files = [
        "backup.tar.gpg.sig",
        "backup.json.gpg.asc",
        "backup.lst.asc",
    ]

    payload, receipt = upload.split_receipt_files(files, "backup")

    assert payload == ["backup.tar.gpg.sig", "backup.json.gpg.asc"]
    assert receipt == "backup.lst.asc"


def test_split_receipt_files_leaves_files_unchanged_without_filelist():
    files = [
        "backup.tar",
        "backup.json",
    ]

    payload, receipt = upload.split_receipt_files(files, "backup")

    assert payload == files
    assert receipt is None
