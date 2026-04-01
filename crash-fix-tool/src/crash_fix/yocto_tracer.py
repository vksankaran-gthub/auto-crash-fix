"""Module for tracing crashing components to Yocto recipes and source repositories."""

import os
import re
import shutil
import subprocess

import click


class YoctoTracer:
    """Traces a component name to its Yocto recipe and source git repository."""

    def __init__(self, cache_dir=None):
        self.cache_dir = cache_dir or os.path.join(
            os.path.expanduser("~"), ".cache", "crash-fix-tool", "repos"
        )

    def find_recipe(self, component_name):
        """Map a crashing component to its Yocto recipe.

        Uses oe-pkgdata-util to find the package, then the recipe.

        Args:
            component_name: Name of the crashing binary/library/script.

        Returns:
            dict with recipe_name and package_name, or None on error.
        """
        if not component_name:
            click.echo("Error: No component name provided", err=True)
            return None

        # Check bitbake availability
        if not self._check_bitbake_available():
            return None

        # Step 1: find-path to get the package
        package_name = self._find_package_for_component(component_name)
        if not package_name:
            click.echo(
                f"Error: Could not map component '{component_name}' to a Yocto recipe",
                err=True,
            )
            return None

        # Step 2: lookup-recipe to get the recipe
        recipe_name = self._lookup_recipe(package_name)
        if not recipe_name:
            click.echo(
                f"Error: Could not find recipe for package '{package_name}'",
                err=True,
            )
            return None

        return {
            "component_name": component_name,
            "package_name": package_name,
            "recipe_name": recipe_name,
        }

    def extract_source_info(self, recipe_name):
        """Extract source repository info from a recipe using bitbake -e.

        Args:
            recipe_name: Yocto recipe name.

        Returns:
            dict with repo_url, srcrev, branch, src_dir, or None on error.
        """
        if not recipe_name:
            return None

        try:
            result = subprocess.run(
                ["bitbake", "-e", recipe_name],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            click.echo(
                "Error: Bitbake not found — run this tool from a configured "
                "Yocto build environment",
                err=True,
            )
            return None
        except subprocess.TimeoutExpired:
            click.echo(
                f"Error: bitbake -e {recipe_name} timed out", err=True
            )
            return None

        output = result.stdout
        if not output:
            click.echo(
                f"Error: bitbake -e {recipe_name} produced no output", err=True
            )
            return None

        # Parse SRC_URI
        src_uri = self._extract_var(output, "SRC_URI")
        if not src_uri:
            click.echo(
                f"Error: Could not extract SRC_URI from recipe '{recipe_name}'",
                err=True,
            )
            return None

        # Check for git source
        repo_url = self._extract_git_url(src_uri)
        if not repo_url:
            click.echo(
                f"Error: Recipe '{recipe_name}' uses non-git source — "
                "manual investigation required",
                err=True,
            )
            return None

        # Parse SRCREV
        srcrev = self._extract_var(output, "SRCREV") or "HEAD"

        # Parse branch from SRC_URI
        branch = self._extract_branch(src_uri)

        # Parse S (source directory)
        src_dir = self._extract_var(output, "S") or ""

        return {
            "recipe_name": recipe_name,
            "repo_url": repo_url,
            "srcrev": srcrev,
            "branch": branch,
            "src_dir": src_dir,
        }

    def clone_or_update_repo(self, repo_url, srcrev="HEAD"):
        """Clone or update a git repository, checking out the given SRCREV.

        Args:
            repo_url: Git repository URL.
            srcrev: Commit hash to checkout.

        Returns:
            Path to the local repo directory, or None on error.
        """
        if not repo_url:
            return None

        # Derive a cache directory name from the repo URL
        repo_name = repo_url.rstrip("/").split("/")[-1]
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]
        repo_dir = os.path.join(self.cache_dir, repo_name)

        os.makedirs(self.cache_dir, exist_ok=True)

        if os.path.isdir(os.path.join(repo_dir, ".git")):
            # Repo exists — fetch and checkout
            click.echo(f"       Using cached repo: {repo_dir}")
            try:
                subprocess.run(
                    ["git", "fetch", "--all"],
                    cwd=repo_dir,
                    capture_output=True,
                    timeout=120,
                )
                subprocess.run(
                    ["git", "checkout", srcrev],
                    cwd=repo_dir,
                    capture_output=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                click.echo("Warning: Git operation timed out", err=True)
        else:
            # Fresh clone
            click.echo(f"       Cloning {repo_url}...")
            try:
                result = subprocess.run(
                    ["git", "clone", repo_url, repo_dir],
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode != 0:
                    click.echo(
                        f"Error: git clone failed: {result.stderr.strip()}",
                        err=True,
                    )
                    return None

                if srcrev and srcrev != "HEAD":
                    subprocess.run(
                        ["git", "checkout", srcrev],
                        cwd=repo_dir,
                        capture_output=True,
                        timeout=30,
                    )
            except subprocess.TimeoutExpired:
                click.echo("Error: git clone timed out", err=True)
                return None

        return repo_dir

    def _check_bitbake_available(self):
        """Check if bitbake is available in PATH."""
        if shutil.which("bitbake") is None:
            click.echo(
                "Error: Bitbake not found — run this tool from a configured "
                "Yocto build environment",
                err=True,
            )
            return False
        return True

    def _find_package_for_component(self, component_name):
        """Use oe-pkgdata-util find-path to get the package for a component."""
        # Try with common paths
        search_paths = [
            f"*/{component_name}",
            f"*/lib/{component_name}",
            f"*/bin/{component_name}",
            f"*/sbin/{component_name}",
            component_name,
        ]

        for path in search_paths:
            try:
                result = subprocess.run(
                    ["oe-pkgdata-util", "find-path", path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    # Output format: "package: path"
                    line = result.stdout.strip().split("\n")[0]
                    package = line.split(":")[0].strip()
                    if package:
                        return package
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue

        return None

    def _lookup_recipe(self, package_name):
        """Use oe-pkgdata-util lookup-recipe to get the recipe for a package."""
        try:
            result = subprocess.run(
                ["oe-pkgdata-util", "lookup-recipe", package_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0].strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    @staticmethod
    def _extract_var(bitbake_output, var_name):
        """Extract a variable value from bitbake -e output."""
        # bitbake -e outputs: VAR="value"
        pattern = rf'^{var_name}="(.+?)"'
        match = re.search(pattern, bitbake_output, re.MULTILINE)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_git_url(src_uri):
        """Extract a git URL from SRC_URI string."""
        if not src_uri:
            return None

        # Match git:// or https:// git URLs
        for part in src_uri.split():
            if part.startswith("git://") or (
                part.startswith("https://") and "git" in part
            ):
                # Strip protocol options like ;branch=xxx;protocol=https
                url = part.split(";")[0]
                return url

        return None

    @staticmethod
    def _extract_branch(src_uri):
        """Extract branch from SRC_URI git parameters."""
        if not src_uri:
            return "main"

        match = re.search(r";branch=([^;\s]+)", src_uri)
        if match:
            return match.group(1)
        return "main"
