"""Pinned SDK history adapter: safe string NodeIds and bounded continuation pages."""

import hashlib

from asyncua.server.history_sql import HistorySQLite


class UaHistorySQLite(HistorySQLite):
    def _get_table_name(self, node_id):
        # SDK 2.0.1 repr(string) contains quotes rejected by its SQL-name validator.
        return "ua_" + hashlib.sha256(node_id.to_string().encode()).hexdigest()

    async def read_node_history(self, node_id, start, end, nb_values):
        limit = min(nb_values or 500, 500)
        values, _ = await super().read_node_history(node_id, start, end, limit + 1)
        continuation = values[limit].SourceTimestamp if len(values) > limit else None
        return values[:limit], continuation
