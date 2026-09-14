"""
evaluation — offline evaluation harness for ClipPods (master plan, Phase 0).

Isolated from the production request path: nothing in routers/ or the job worker
imports this package. It runs pipeline stages on local media files, caches
expensive stage outputs by content hash, runs one or more selection engines and
writes versioned run artifacts under the evaluation data directory.

Usage: see backend/evaluation/README.md
"""
