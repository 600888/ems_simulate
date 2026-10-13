"""Resolve DataSet member types from their owning LN and DA/BDA templates."""

from __future__ import annotations

from ....defs.address import infer_iec_type_from_address
from ..model.enums import FC_TO_IEC_TYPE, iec_type_from_btype
from ..model.scl_document import SclDocument, SclFCDA

_SCALAR_TYPES = frozenset({"boolean", "integer", "float", "string", "bitstring", "timestamp"})


def infer_fcda_iec_type(member: dict[str, str]) -> str:
    """Prefer declared types, then attribute paths, retaining FC as a legacy fallback."""
    declared_type = iec_type_from_btype(member.get("b_type", ""))
    if declared_type in _SCALAR_TYPES:
        return declared_type
    if member.get("iec_type") in _SCALAR_TYPES:
        return member["iec_type"]

    da_path = member.get("da_name", "")
    ref = member.get("fcda_ref", "") or f"LD/LN.DO.{da_path}"
    # Quality is a packed MMS bit string; generic point-address inference
    # represents it as an integer for point storage.
    if da_path == "q" or ref.endswith(".q"):
        return "bitstring"
    inferred_type = infer_iec_type_from_address(ref)
    if inferred_type in _SCALAR_TYPES:
        return inferred_type
    return FC_TO_IEC_TYPE.get(member.get("fc", ""), "boolean")


class DataSetTypeResolver:
    """Index LN instances per IED so identical LD/LN names cannot cross-contaminate types."""

    def __init__(self, doc: SclDocument):
        self._doc = doc
        self._ln_types: dict[tuple[str, str, str], str] = {}
        for ied in doc.ieds:
            for ap in ied.access_points:
                if ap.server is None:
                    continue
                for ld in ap.server.ldevices:
                    logical_nodes = ([ld.ln0] if ld.ln0 else []) + ld.lns
                    for ln in logical_nodes:
                        self._ln_types[(ied.name, ld.inst, ln.ln_name)] = ln.ln_type

    def resolve_btype(self, fcda: SclFCDA, ied_name: str) -> str:
        """Follow DO/SDO and arbitrary-depth DA/BDA paths to the declared bType."""
        ln_name = "LLN0" if fcda.ln_class == "LLN0" else f"{fcda.ln_prefix}{fcda.ln_class}{fcda.ln_inst}"
        ln_type_id = self._ln_types.get((ied_name, fcda.ld_inst, ln_name), "")
        ln_type = self._doc.get_ln_node_type(ln_type_id)
        if ln_type is None or not fcda.do_name or not fcda.da_name:
            return ""

        do_parts = fcda.do_name.split(".")
        do_def = next((item for item in ln_type.dos if item.name == do_parts[0]), None)
        if do_def is None:
            return ""
        do_type = self._doc.get_do_type(do_def.type_id)
        for name in do_parts[1:]:
            if do_type is None:
                return ""
            sdo = next((item for item in do_type.sdos if item.name == name), None)
            do_type = self._doc.get_do_type(sdo.type_id) if sdo else None
        if do_type is None:
            return ""

        # Some models include SDO components at the start of daName.
        da_parts = fcda.da_name.split(".")
        attribute = None
        for index, name in enumerate(da_parts):
            attribute = next((item for item in do_type.das if item.name == name), None)
            if attribute is not None:
                da_parts = da_parts[index + 1 :]
                break
            sdo = next((item for item in do_type.sdos if item.name == name), None)
            do_type = self._doc.get_do_type(sdo.type_id) if sdo else None
            if do_type is None:
                return ""
        if attribute is None:
            return ""

        for name in da_parts:
            if attribute.b_type.strip().upper() != "STRUCT":
                return ""
            da_type = self._doc.get_da_type(attribute.type_id)
            if da_type is None:
                return ""
            attribute = next((item for item in da_type.bdas if item.name == name), None)
            if attribute is None:
                return ""
        return attribute.b_type

    def resolve_iec_type(self, fcda: SclFCDA, ied_name: str) -> str:
        """Return the scalar import type for a member, with incomplete-SCL fallbacks."""
        return infer_fcda_iec_type(
            {
                "b_type": self.resolve_btype(fcda, ied_name),
                "da_name": fcda.da_name,
                "fcda_ref": fcda.fcda_ref,
                "fc": fcda.fc,
            }
        )
