"""Issue classification, CWE taxonomy mapping, and severity normalization."""

from typing import Dict, Optional, Tuple
from app.analysis.schemas import IssueCategory, IssueSeverity

# Comprehensive mapping of common software security and logic weaknesses to CWE taxonomy
CWE_TAXONOMY: Dict[str, Tuple[str, str, IssueSeverity]] = {
    # Security Vulnerabilities (OWASP Top 10)
    "sql_injection": ("CWE-89", "SQL Injection", "Critical"),
    "sqli": ("CWE-89", "SQL Injection", "Critical"),
    "command_injection": ("CWE-78", "OS Command Injection", "Critical"),
    "path_traversal": ("CWE-22", "Path Traversal", "High"),
    "zip_slip": ("CWE-22", "Path Traversal (Zip Slip)", "High"),
    "hardcoded_credentials": ("CWE-798", "Hardcoded Credentials or Secrets", "High"),
    "hardcoded_secret": ("CWE-798", "Hardcoded Secret", "High"),
    "cross_site_scripting": ("CWE-79", "Cross-site Scripting (XSS)", "High"),
    "xss": ("CWE-79", "Cross-site Scripting (XSS)", "High"),
    "insecure_deserialization": ("CWE-502", "Insecure Deserialization", "High"),
    "missing_authorization": ("CWE-862", "Missing Authorization Check", "High"),
    "broken_authentication": ("CWE-287", "Improper Authentication", "High"),
    "sensitive_data_exposure": ("CWE-200", "Exposure of Sensitive Information", "Medium"),
    "weak_cryptography": ("CWE-327", "Use of Broken or Weak Cryptography", "Medium"),
    "ssrf": ("CWE-918", "Server-Side Request Forgery", "High"),
    "open_redirect": ("CWE-601", "URL Redirection to Untrusted Site", "Medium"),
    "unsafe_file_upload": ("CWE-434", "Unrestricted Upload of Dangerous File", "High"),

    # Logic & Runtime Bugs
    "division_by_zero": ("CWE-369", "Divide By Zero", "High"),
    "null_dereference": ("CWE-476", "Null / None Pointer Dereference", "High"),
    "unhandled_none": ("CWE-476", "Unhandled None Return / Attribute Error", "Medium"),
    "off_by_one": ("CWE-193", "Off-by-one Error", "Medium"),
    "infinite_loop": ("CWE-835", "Loop with Unreachable Exit Condition", "High"),
    "unhandled_exception": ("CWE-755", "Improper Exception Handling", "Medium"),
    "incorrect_condition": ("CWE-670", "Always True/False Conditional Logic", "Medium"),
    "unreachable_code": ("CWE-561", "Dead / Unreachable Code", "Low"),
    "race_condition": ("CWE-362", "Concurrent Race Condition", "High"),

    # Code Smells & Maintainability
    "dead_code": ("CWE-561", "Dead / Unused Code", "Low"),
    "unused_variable": ("CWE-563", "Assignment to Variable without Use", "Low"),
    "cognitive_complexity": ("CWE-1120", "Excessive Cognitive Complexity", "Low"),
    "excessive_parameters": ("CWE-1120", "Excessive Parameter Count", "Informational"),
    "code_duplication": ("CWE-1041", "Redundant Code Duplication", "Low"),
}

VALID_SEVERITIES = {"Critical", "High", "Medium", "Low", "Informational"}
VALID_CATEGORIES = {"logic_bug", "security_vulnerability", "code_smell"}


class IssueClassifier:
    """Normalizes issue categories, severity levels, and CWE mappings."""

    def normalize_classification(
        self,
        category: str,
        subcategory: Optional[str],
        severity: str,
        issue_title: str,
    ) -> Tuple[IssueCategory, Optional[str], IssueSeverity, Optional[str]]:
        """Validates and normalizes category, severity, and CWE mapping.

        Returns:
            Tuple of (normalized_category, normalized_subcategory, normalized_severity, cwe_id).
        """
        # 1. Normalize Category
        clean_cat = category.lower().strip()
        if "security" in clean_cat or "vuln" in clean_cat or "cwe" in clean_cat:
            norm_category: IssueCategory = "security_vulnerability"
        elif "smell" in clean_cat or "style" in clean_cat or "complexity" in clean_cat:
            norm_category = "code_smell"
        else:
            norm_category = "logic_bug"

        # 2. Match CWE taxonomy from subcategory or title keywords
        clean_sub = (subcategory or "").lower().replace("-", "_").replace(" ", "_")
        cwe_id = None
        matched_severity = None

        if clean_sub in CWE_TAXONOMY:
            cwe_id, _, matched_severity = CWE_TAXONOMY[clean_sub]
        else:
            # Keyword matching from title
            title_lower = issue_title.lower()
            for key, (cand_cwe, _, cand_sev) in CWE_TAXONOMY.items():
                token = key.replace("_", " ")
                if token in title_lower:
                    cwe_id = cand_cwe
                    clean_sub = key
                    matched_severity = cand_sev
                    break

        # 3. Normalize Severity
        clean_sev = severity.capitalize().strip()
        if clean_sev not in VALID_SEVERITIES:
            clean_sev = matched_severity or ("High" if norm_category == "security_vulnerability" else "Medium")

        # If it's a known critical CWE (SQLi, command injection), ensure appropriate baseline severity
        if cwe_id in ("CWE-89", "CWE-78") and clean_sev in ("Low", "Informational"):
            clean_sev = "Critical"

        return norm_category, clean_sub or None, clean_sev, cwe_id  # type: ignore[return-value]


default_classifier = IssueClassifier()

