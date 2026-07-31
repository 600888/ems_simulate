"""Web API package.

Routers are imported explicitly by :mod:`src.web.app`. Keeping this package
initializer side-effect free prevents schema imports from recursively loading
the complete route graph.
"""
