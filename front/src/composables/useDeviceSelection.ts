import { computed, ref, type ComputedRef } from "vue";

/** Keep selection independent of the displayed page and resolve current row data. */
export function useDeviceSelection<T extends { id: number }>(
  rows: ComputedRef<T[]>,
  filteredRows: ComputedRef<T[]>,
) {
  const selectedIds = ref(new Set<number>());
  const selected = computed(() =>
    rows.value.filter((row) => selectedIds.value.has(row.id)),
  );
  const selectedCount = computed(
    () =>
      filteredRows.value.filter((row) => selectedIds.value.has(row.id)).length,
  );
  const allSelected = computed(
    () =>
      filteredRows.value.length > 0 &&
      selectedCount.value === filteredRows.value.length,
  );
  const partiallySelected = computed(
    () => selectedCount.value > 0 && !allSelected.value,
  );

  function clearSelection() {
    selectedIds.value = new Set();
  }
  function selectAll(checked: boolean) {
    selectedIds.value = new Set(
      checked ? filteredRows.value.map((row) => row.id) : [],
    );
  }
  function selectDevice(id: number, checked: boolean) {
    if (checked) selectedIds.value.add(id);
    else selectedIds.value.delete(id);
  }

  return {
    selectedIds,
    selected,
    allSelected,
    partiallySelected,
    clearSelection,
    selectAll,
    selectDevice,
  };
}
