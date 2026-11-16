import { computed, ref } from "vue";
import { useDeviceSelection } from "@/composables/useDeviceSelection";

function setupSelection() {
  const rows = ref(
    Array.from({ length: 21 }, (_, i) => ({
      id: i + 1,
      name: `device-${i + 1}`,
    })),
  );
  const allowedIds = ref<number[] | null>(null);
  const filteredRows = computed(() =>
    rows.value.filter(
      (row) => allowedIds.value === null || allowedIds.value.includes(row.id),
    ),
  );
  return {
    rows,
    filteredRows,
    allowedIds,
    ...useDeviceSelection(
      computed(() => rows.value),
      filteredRows,
    ),
  };
}

it("selects every matching device across pages and clears every page together", () => {
  const selection = setupSelection();
  selection.selectAll(true);
  expect(selection.selected.value).toHaveLength(21);
  expect(selection.allSelected.value).toBe(true);
  for (let page = 0; page < 3; page++) {
    const pageRows = selection.filteredRows.value.slice(
      page * 8,
      (page + 1) * 8,
    );
    expect(
      pageRows.every((row) => selection.selectedIds.value.has(row.id)),
    ).toBe(true);
  }
  selection.selectAll(false);
  expect(selection.selected.value).toEqual([]);
  expect(selection.allSelected.value).toBe(false);
  expect(selection.partiallySelected.value).toBe(false);
});

it("limits select all to the current filtered scope", () => {
  const selection = setupSelection();
  selection.allowedIds.value = [2, 5, 9, 12, 17, 21];
  selection.selectAll(true);
  expect(selection.selected.value.map((row) => row.id)).toEqual([
    2, 5, 9, 12, 17, 21,
  ]);
  expect(selection.selectedIds.value.has(1)).toBe(false);
  expect(selection.allSelected.value).toBe(true);
  selection.clearSelection();
  expect(selection.selected.value).toEqual([]);
});

it("keeps selections across pages and updates the header after a single deselection", () => {
  const selection = setupSelection();
  selection.selectDevice(1, true);
  selection.selectDevice(17, true);
  expect(selection.selected.value.map((row) => row.id)).toEqual([1, 17]);
  expect(selection.partiallySelected.value).toBe(true);
  selection.selectAll(true);
  selection.selectDevice(17, false);
  expect(selection.selected.value).toHaveLength(20);
  expect(selection.selectedIds.value.has(17)).toBe(false);
  expect(selection.partiallySelected.value).toBe(true);
  expect(selection.allSelected.value).toBe(false);
});

it("uses refreshed data for selected devices and excludes removed devices", () => {
  const selection = setupSelection();
  selection.selectAll(true);
  selection.rows.value = [{ id: 17, name: "updated device" }];
  expect(selection.selected.value).toEqual([
    { id: 17, name: "updated device" },
  ]);
  selection.rows.value = [];
  selection.selectAll(true);
  expect(selection.selected.value).toEqual([]);
  expect(selection.allSelected.value).toBe(false);
  expect(selection.partiallySelected.value).toBe(false);
});
