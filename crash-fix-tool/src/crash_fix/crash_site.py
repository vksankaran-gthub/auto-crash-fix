"""Module for locating crash sites in source code from backtrace data."""

import os
import re

import click


class CrashSiteLocator:
    """Locates crash sites in source code using backtrace information."""

    # Number of lines of context to extract around the crash site
    CONTEXT_LINES = 50

    def locate_crash_source(self, backtrace, repo_path):
        """Find source files in the repo matching backtrace frames.

        Args:
            backtrace: List of stack frame dicts from portal.
            repo_path: Path to the cloned source repository.

        Returns:
            List of crash site dicts with file path, line number,
            function name, and source context. Returns None if no match.
        """
        if not backtrace or not repo_path:
            return None

        crash_sites = []

        for frame in backtrace:
            source_file = frame.get("source_file", "")
            line_number = frame.get("line_number")
            function_name = frame.get("function_name", "")

            if not source_file:
                continue

            # Try exact path match first
            full_path = self._find_source_file(source_file, repo_path)

            if not full_path:
                # Fallback: match by filename only
                basename = os.path.basename(source_file)
                full_path = self._find_by_filename(basename, repo_path)

                if not full_path:
                    click.echo(
                        f"Warning: Source file '{source_file}' not found in repo",
                        err=True,
                    )
                    continue

            # Extract source context
            context = self._extract_context(full_path, line_number)

            crash_sites.append(
                {
                    "source_file": os.path.relpath(full_path, repo_path),
                    "original_path": source_file,
                    "line_number": line_number,
                    "function_name": function_name,
                    "source_context": context,
                    "frame_number": frame.get("frame_number", 0),
                }
            )

        return crash_sites if crash_sites else None

    def classify_crash_type(self, backtrace, metadata):
        """Classify the crash type from backtrace and metadata.

        Args:
            backtrace: List of stack frame dicts.
            metadata: Crash metadata dict.

        Returns:
            str: One of "segfault", "abort", "unknown".
        """
        # Check backtrace for signal indicators
        all_text = ""
        for frame in backtrace:
            fn = frame.get("function_name", "")
            all_text += f" {fn}"

        # Check for SIGSEGV indicators
        sigsegv_patterns = ["SIGSEGV", "sigsegv", "segfault", "segmentation"]
        for pattern in sigsegv_patterns:
            if pattern.lower() in all_text.lower():
                return "segfault"

        # Check for SIGABRT indicators
        sigabrt_patterns = ["SIGABRT", "sigabrt", "abort", "__assert_fail", "raise"]
        for pattern in sigabrt_patterns:
            if pattern.lower() in all_text.lower():
                return "abort"

        # Check metadata for crash type hints
        component_type = metadata.get("component_type", "")
        if component_type == "script":
            return "script_error"

        return "unknown"

    def _find_source_file(self, source_path, repo_path):
        """Find a source file in the repo by its path.

        Handles cases where the backtrace path is absolute or has
        build-directory prefixes.
        """
        # Try direct join
        candidate = os.path.join(repo_path, source_path)
        if os.path.isfile(candidate):
            return candidate

        # Try stripping leading path components until we find a match
        parts = source_path.replace("\\", "/").split("/")
        for i in range(len(parts)):
            candidate = os.path.join(repo_path, *parts[i:])
            if os.path.isfile(candidate):
                return candidate

        return None

    def _find_by_filename(self, filename, repo_path):
        """Search for a file by name anywhere in the repo."""
        for root, _dirs, files in os.walk(repo_path):
            # Skip .git directory
            if ".git" in root.split(os.sep):
                continue
            if filename in files:
                return os.path.join(root, filename)
        return None

    def _extract_context(self, file_path, line_number):
        """Extract source code context around a line number.

        Returns the crashing function plus CONTEXT_LINES before and after.
        """
        try:
            with open(file_path, "r", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return None

        if not lines:
            return None

        total_lines = len(lines)

        if line_number is None or line_number < 1:
            # Return first 100 lines as general context
            end = min(100, total_lines)
            return {
                "start_line": 1,
                "end_line": end,
                "code": "".join(lines[:end]),
            }

        # 0-indexed
        crash_idx = line_number - 1
        start = max(0, crash_idx - self.CONTEXT_LINES)
        end = min(total_lines, crash_idx + self.CONTEXT_LINES + 1)

        return {
            "start_line": start + 1,
            "end_line": end,
            "crash_line": line_number,
            "code": "".join(lines[start:end]),
        }
