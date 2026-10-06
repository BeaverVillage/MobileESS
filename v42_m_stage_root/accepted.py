"""Native OPTIMAL alone cannot identify an audited scientific RMP point."""
def accepted_rmp(row):
    return bool(row.get('status')==2 and row.get('point_file') and row.get('point_SHA')
        and row.get('dual_SHA') and row.get('objective') is not None)
