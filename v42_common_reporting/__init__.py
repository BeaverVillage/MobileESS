"""Evidence-derived May reports; this package never modifies scientific inputs."""

def summarize(campaign_root, manifest_path=None, output_root=None):
    from .report import summarize as build_snapshot
    return build_snapshot(campaign_root, manifest_path, output_root)

__all__ = ["summarize"]
