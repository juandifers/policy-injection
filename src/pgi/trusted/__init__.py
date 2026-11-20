"""Code that reads TRUSTED inputs only (invariant 4: nothing here accepts an untrusted field). The resolver lives here so the
boundary is visible in the tree: it feeds a trusted compiler and never sees manifests, descriptions or generated text."""
