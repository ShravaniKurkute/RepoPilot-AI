"""Call graph resolution linking caller sites to callee symbols."""

from typing import Dict, List, Optional, Tuple

from app.code_analysis.schemas import CallGraphEdge, ImportStatement, Symbol


def _normalize_name(name: str) -> str:
    """Extracts base function or method name from attribute or chained call syntax."""
    # e.g. "self.do_something" -> "do_something", "obj.method" -> "method"
    if "." in name:
        return name.split(".")[-1]
    return name


class CallGraphResolver:
    """Resolves function/method invocation sites to concrete symbol definitions."""

    def __init__(
        self,
        symbols_by_file: Dict[str, List[Symbol]],
        imports_by_file: Dict[str, List[ImportStatement]],
    ):
        self.symbols_by_file = symbols_by_file
        self.imports_by_file = imports_by_file

        # Lookup: file_path -> name -> Symbol
        self._file_symbol_map: Dict[str, Dict[str, Symbol]] = {}
        for file_path, sym_list in symbols_by_file.items():
            name_map = {}
            for s in sym_list:
                name_map[s.name] = s
            self._file_symbol_map[file_path] = name_map

        # Global symbol lookup: name -> List[Symbol]
        self._global_symbol_map: Dict[str, List[Symbol]] = {}
        for sym_list in symbols_by_file.values():
            for s in sym_list:
                self._global_symbol_map.setdefault(s.name, []).append(s)

    def resolve_edges(self, edges: List[CallGraphEdge]) -> Tuple[List[CallGraphEdge], int]:
        """Resolves call graph edges to callee symbol definitions.

        Args:
            edges: List of raw call graph edges.

        Returns:
            Tuple of (resolved_edges, resolved_count).
        """
        resolved_edges: List[CallGraphEdge] = []
        resolved_count = 0

        for edge in edges:
            file_path = edge.caller_file
            callee_raw = edge.callee_name
            base_callee = _normalize_name(callee_raw)

            resolved_sym: Optional[Symbol] = None

            # 1. Local resolution in the same file
            file_symbols = self._file_symbol_map.get(file_path, {})
            if base_callee in file_symbols:
                resolved_sym = file_symbols[base_callee]

            # 2. Cross-file resolution via imports
            if not resolved_sym and file_path in self.imports_by_file:
                for imp in self.imports_by_file[file_path]:
                    if not imp.resolved_target_file:
                        continue

                    target_symbols = self._file_symbol_map.get(imp.resolved_target_file, {})

                    # Direct imported name: from module import foo
                    if base_callee in imp.names:
                        if base_callee in target_symbols:
                            resolved_sym = target_symbols[base_callee]
                            break

                    # Aliased import: from module import bar as foo
                    for orig_name, alias in imp.aliases.items():
                        if alias == base_callee and orig_name in target_symbols:
                            resolved_sym = target_symbols[orig_name]
                            break
                    if resolved_sym:
                        break

                    # Module member access: import module; module.foo()
                    if "." in callee_raw:
                        parts = callee_raw.split(".")
                        mod_prefix = parts[0]
                        member_name = parts[-1]
                        if mod_prefix == imp.module or mod_prefix in imp.names:
                            if member_name in target_symbols:
                                resolved_sym = target_symbols[member_name]
                                break

            # 3. Unique global symbol fallback if unambiguous
            if not resolved_sym:
                global_matches = self._global_symbol_map.get(base_callee, [])
                if len(global_matches) == 1:
                    resolved_sym = global_matches[0]

            if resolved_sym:
                resolved_count += 1
                resolved_edges.append(
                    edge.model_copy(
                        update={
                            "is_resolved": True,
                            "resolved_callee_id": resolved_sym.id,
                            "resolved_callee_file": resolved_sym.file_path,
                        }
                    )
                )
            else:
                resolved_edges.append(edge)

        return resolved_edges, resolved_count

