"""Regression tests for DataSet member-level pagination."""

from src.web.api.channel.iec61850 import _paginate_iec61850_dataset_tree


def _tree() -> dict:
    return {
        "items": [
            {
                "do_ref": "LD0/LLN0.Do1",
                "children": [{"da_path": f"a{i}"} for i in range(3)],
            },
            {
                "do_ref": "LD0/LLN0.Do2",
                "children": [{"da_path": f"b{i}"} for i in range(4)],
            },
        ],
        # The old value counted DO groups, not the visible member rows.
        "total": 2,
    }


def test_dataset_tree_paginates_visible_member_rows_across_do_groups():
    page = _paginate_iec61850_dataset_tree(_tree(), page_index=2, page_size=3)

    assert page["total"] == 7
    assert [item["do_ref"] for item in page["items"]] == ["LD0/LLN0.Do2"]
    assert [child["da_path"] for child in page["items"][0]["children"]] == [
        "b0",
        "b1",
        "b2",
    ]


def test_dataset_tree_page_can_span_do_groups_without_exceeding_page_size():
    page = _paginate_iec61850_dataset_tree(_tree(), page_index=1, page_size=4)

    assert page["total"] == 7
    assert [len(item["children"]) for item in page["items"]] == [3, 1]
    assert sum(len(item["children"]) for item in page["items"]) == 4


def test_dataset_tree_returns_empty_items_past_last_page_with_full_total():
    page = _paginate_iec61850_dataset_tree(_tree(), page_index=4, page_size=3)

    assert page == {"items": [], "total": 7}
