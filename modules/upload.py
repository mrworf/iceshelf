def split_receipt_files(files, backup_name):
    """Return (payload_files, receipt_file) for a prepared backup file list."""
    receipt_base = backup_name + ".lst"
    signed_receipt = receipt_base + ".asc"

    receipt = None
    if signed_receipt in files:
        receipt = signed_receipt
    elif receipt_base in files:
        receipt = receipt_base

    if receipt is None:
        return files, None

    payload_files = [f for f in files if f != receipt]
    return payload_files, receipt
