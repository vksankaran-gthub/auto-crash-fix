"""CLI entry point for crash-fix-tool."""

import json
import os
import sys

import click

from crash_fix.config import Config
from crash_fix.portal_client import PortalClient
from crash_fix.yocto_tracer import YoctoTracer
from crash_fix.crash_site import CrashSiteLocator
from crash_fix.ai_fix_generator import AIFixGenerator
from crash_fix.build_validator import BuildValidator
from crash_fix.device_tester import DeviceTester
from crash_fix.regression_checker import RegressionChecker
from crash_fix.pr_creator import PRCreator


@click.group()
@click.pass_context
def main(ctx):
    """Automated crash fix and PR generation from stack trace portal fingerprints."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config()


@main.command()
@click.argument("fingerprint_id")
@click.pass_context
def lookup(ctx, fingerprint_id):
    """Look up a crash fingerprint and trace it to the source repository.

    Runs the Phase 1 pipeline: fetch crash metadata, trace to Yocto recipe
    and source repo, retrieve backtrace, and identify crash site in source.
    """
    config = ctx.obj["config"]

    # Validate portal credentials
    valid, error = config.validate_portal_credentials()
    if not valid:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    portal = PortalClient(config.portal_url, config.portal_token)

    # Step 1: Fetch crash metadata
    click.echo(f"[1/4] Fetching crash metadata for fingerprint: {fingerprint_id}")
    metadata = portal.get_crash_metadata(fingerprint_id)
    if metadata is None:
        sys.exit(1)

    click.echo(f"       Component: {metadata.get('component_name', 'unknown')} "
               f"({metadata.get('component_type', 'unknown')})")
    click.echo(f"       Build: {metadata.get('build_version', 'unknown')}")

    # Step 2: Fetch backtrace
    click.echo(f"[2/4] Fetching backtrace...")
    backtrace = portal.get_backtrace(fingerprint_id)

    # Step 3: Trace to Yocto recipe and source repo
    click.echo(f"[3/4] Tracing component to source repository...")
    tracer = YoctoTracer(cache_dir=config.cache_dir)
    component_name = metadata.get("component_name", "")

    recipe_info = tracer.find_recipe(component_name)
    if recipe_info is None:
        sys.exit(1)

    source_info = tracer.extract_source_info(recipe_info["recipe_name"])
    if source_info is None:
        sys.exit(1)

    repo_path = tracer.clone_or_update_repo(
        source_info["repo_url"], source_info.get("srcrev", "HEAD")
    )
    if repo_path is None:
        sys.exit(1)

    # Step 4: Identify crash site in source
    click.echo(f"[4/4] Identifying crash site in source code...")
    locator = CrashSiteLocator()
    crash_site = None
    if backtrace:
        crash_site = locator.locate_crash_source(backtrace, repo_path)

    # Build report
    crash_type = "unknown"
    if backtrace:
        crash_type = locator.classify_crash_type(backtrace, metadata)

    report = {
        "fingerprint_id": fingerprint_id,
        "crash_metadata": metadata,
        "crash_type": crash_type,
        "recipe_info": recipe_info,
        "source_info": source_info,
        "repo_path": repo_path,
        "backtrace": backtrace,
        "crash_site": crash_site,
    }

    click.echo("\n" + json.dumps(report, indent=2, default=str))


@main.command("generate-fix")
@click.argument("fingerprint_id")
@click.option("--dry-run", is_flag=True, help="Show prompt and response without applying patch")
@click.pass_context
def generate_fix(ctx, fingerprint_id, dry_run):
    """Generate an AI-assisted fix for a crash (Phase 1 + Phase 2)."""
    config = ctx.obj["config"]

    # Validate portal credentials
    valid, error = config.validate_portal_credentials()
    if not valid:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    portal = PortalClient(config.portal_url, config.portal_token)

    # Phase 1: Lookup
    click.echo(f"[1/6] Fetching crash metadata for fingerprint: {fingerprint_id}")
    metadata = portal.get_crash_metadata(fingerprint_id)
    if metadata is None:
        click.echo("Error: Could not fetch crash metadata.", err=True)
        sys.exit(1)

    click.echo(f"[2/6] Fetching backtrace...")
    backtrace = portal.get_backtrace(fingerprint_id)

    click.echo(f"[3/6] Tracing component to source repository...")
    tracer = YoctoTracer(cache_dir=config.cache_dir)
    component_name = metadata.get("component_name", "")

    recipe_info = tracer.find_recipe(component_name)
    if recipe_info is None:
        click.echo("Error: Could not find Yocto recipe.", err=True)
        sys.exit(1)

    source_info = tracer.extract_source_info(recipe_info["recipe_name"])
    if source_info is None:
        click.echo("Error: Could not extract source info.", err=True)
        sys.exit(1)

    repo_path = tracer.clone_or_update_repo(
        source_info["repo_url"], source_info.get("srcrev", "HEAD")
    )
    if repo_path is None:
        click.echo("Error: Could not clone source repo.", err=True)
        sys.exit(1)

    click.echo(f"[4/6] Identifying crash site in source code...")
    locator = CrashSiteLocator()
    crash_site = None
    if backtrace:
        crash_site = locator.locate_crash_source(backtrace, repo_path)

    crash_type = "unknown"
    if backtrace:
        crash_type = locator.classify_crash_type(backtrace, metadata)

    crash_context = {
        "fingerprint_id": fingerprint_id,
        "crash_metadata": metadata,
        "crash_type": crash_type,
        "recipe_info": recipe_info,
        "source_info": source_info,
        "repo_path": repo_path,
        "backtrace": backtrace,
        "crash_site": crash_site,
    }

    # Phase 2: AI fix generation
    click.echo(f"[5/6] Generating AI-assisted fix...")
    generator = AIFixGenerator()
    prompt = generator.build_prompt(crash_context)

    if dry_run:
        click.echo("\n--- Generated Prompt ---")
        click.echo(prompt)

    ai_response = generator.send_to_ai(prompt)
    if ai_response is None:
        click.echo("Error: AI API returned no response.", err=True)
        sys.exit(1)

    if dry_run:
        click.echo("\n--- AI Response ---")
        click.echo(ai_response)
        click.echo("\n(Dry run — patch not applied)")
        sys.exit(0)

    parsed = generator.parse_response(ai_response)
    if not parsed["patch"]:
        click.echo("AI response did not contain an actionable patch.")
        click.echo(f"Explanation: {parsed['explanation']}")
        sys.exit(AIFixGenerator.EXIT_NO_FIX)

    click.echo(f"[6/6] Applying patch...")
    success = generator.apply_patch(parsed["patch"], repo_path, fingerprint_id)

    confidence = generator.assess_confidence(crash_context, parsed)

    result = {
        "fingerprint_id": fingerprint_id,
        "crash_type": crash_type,
        "patch_applied": success,
        "confidence": confidence,
        "files_modified": parsed["files_modified"],
        "explanation": parsed["explanation"],
        "repo_path": repo_path,
    }

    if not success:
        click.echo("Warning: Patch failed to apply cleanly.", err=True)

    click.echo("\n" + json.dumps(result, indent=2, default=str))


@main.command("auto-pr")
@click.argument("fingerprint_id")
@click.option("--skip-tests", is_flag=True, help="Skip device testing")
@click.option("--skip-build", is_flag=True, help="Skip build and PR, generate fix only")
@click.pass_context
def auto_pr(ctx, fingerprint_id, skip_tests, skip_build):
    """Full pipeline: lookup, fix, build, test, and create PR (Phase 1+2+3)."""
    config = ctx.obj["config"]

    # Validate credentials
    valid, error = config.validate_portal_credentials()
    if not valid:
        click.echo(f"Error: {error}", err=True)
        sys.exit(1)

    if not skip_build:
        valid, error = config.validate_github_credentials()
        if not valid:
            click.echo(f"Error: {error}", err=True)
            sys.exit(1)

    portal = PortalClient(config.portal_url, config.portal_token)

    # Phase 1: Lookup
    click.echo(f"[Phase 1] Crash lookup for fingerprint: {fingerprint_id}")
    metadata = portal.get_crash_metadata(fingerprint_id)
    if metadata is None:
        click.echo("Error: Could not fetch crash metadata.", err=True)
        sys.exit(1)

    backtrace = portal.get_backtrace(fingerprint_id)

    tracer = YoctoTracer(cache_dir=config.cache_dir)
    component_name = metadata.get("component_name", "")

    recipe_info = tracer.find_recipe(component_name)
    if recipe_info is None:
        click.echo("Error: Could not find Yocto recipe.", err=True)
        sys.exit(1)

    source_info = tracer.extract_source_info(recipe_info["recipe_name"])
    if source_info is None:
        click.echo("Error: Could not extract source info.", err=True)
        sys.exit(1)

    repo_path = tracer.clone_or_update_repo(
        source_info["repo_url"], source_info.get("srcrev", "HEAD")
    )
    if repo_path is None:
        click.echo("Error: Could not clone source repo.", err=True)
        sys.exit(1)

    locator = CrashSiteLocator()
    crash_site = None
    if backtrace:
        crash_site = locator.locate_crash_source(backtrace, repo_path)

    crash_type = "unknown"
    if backtrace:
        crash_type = locator.classify_crash_type(backtrace, metadata)

    crash_context = {
        "fingerprint_id": fingerprint_id,
        "crash_metadata": metadata,
        "crash_type": crash_type,
        "recipe_info": recipe_info,
        "source_info": source_info,
        "repo_path": repo_path,
        "backtrace": backtrace,
        "crash_site": crash_site,
    }

    # Phase 2: AI fix generation
    click.echo(f"[Phase 2] Generating AI-assisted fix...")
    generator = AIFixGenerator()
    prompt = generator.build_prompt(crash_context)
    ai_response = generator.send_to_ai(prompt)
    if ai_response is None:
        click.echo("Error: AI API returned no response.", err=True)
        sys.exit(1)

    parsed = generator.parse_response(ai_response)
    if not parsed["patch"]:
        click.echo("AI response did not contain an actionable patch.")
        sys.exit(AIFixGenerator.EXIT_NO_FIX)

    patch_result = generator.apply_patch(parsed["patch"], repo_path, fingerprint_id)
    confidence = generator.assess_confidence(crash_context, parsed)

    if not patch_result.get("success"):
        click.echo(f"Error: {patch_result.get('error', 'Patch failed')}", err=True)
        sys.exit(1)

    branch_name = patch_result.get("branch_name", f"crash-fix/{fingerprint_id}")

    if skip_build:
        click.echo("--skip-build: stopping after fix generation.")
        result = {
            "fingerprint_id": fingerprint_id,
            "crash_type": crash_type,
            "confidence": confidence,
            "files_modified": parsed["files_modified"],
            "branch": branch_name,
            "repo_path": repo_path,
        }
        click.echo("\n" + json.dumps(result, indent=2, default=str))
        sys.exit(0)

    # Phase 3: Build, test, PR
    click.echo(f"[Phase 3] Triggering build...")
    builder = BuildValidator(
        ci_url=os.environ.get("CI_URL", ""),
        ci_token=os.environ.get("CI_TOKEN", ""),
    )
    build_trigger = builder.trigger_build(
        recipe_info["recipe_name"],
        branch_name,
        source_info["repo_url"],
    )
    if not build_trigger.get("job_id"):
        click.echo(f"Error: {build_trigger.get('error', 'Build trigger failed')}", err=True)
        sys.exit(1)

    build_result = builder.monitor_build(build_trigger["job_id"])
    if build_result["status"] != "success":
        click.echo(f"Error: {build_result.get('error', 'Build failed')}", err=True)
        sys.exit(1)

    # Device testing
    test_result = {"tests_defined": False, "total": 0, "passed": 0, "failed": 0, "skipped": 0, "results": []}
    regression_result = {"status": "pass", "crashes_found": [], "original_reoccurred": False, "new_fingerprints": []}
    device_id = None

    if not skip_tests:
        click.echo("Deploying to test device...")
        tester = DeviceTester(
            device_pool_url=os.environ.get("DEVICE_POOL_URL", ""),
            device_pool_token=os.environ.get("DEVICE_POOL_TOKEN", ""),
        )

        acquire = tester.acquire_device(metadata.get("device_type", "generic"))
        if acquire.get("device_id"):
            device_id = acquire["device_id"]
            try:
                deploy = tester.deploy_image(device_id, build_result.get("artifact_url", ""))
                if deploy["success"]:
                    click.echo("Running component tests...")
                    test_result = tester.run_component_tests(device_id, component_name)

                    click.echo("Running crash regression check...")
                    checker = RegressionChecker(config.portal_url, config.portal_token)
                    regression_result = checker.monitor_crashes(
                        device_id, fingerprint_id
                    )
                else:
                    click.echo(f"Warning: {deploy.get('error')}", err=True)
            finally:
                tester.release_device(device_id)
        else:
            click.echo(f"Warning: {acquire.get('error')}", err=True)

    # PR creation gate
    pr_creator = PRCreator()
    allowed, reason = pr_creator.can_create_pr(build_result, test_result, regression_result)
    if not allowed:
        click.echo(f"Error: {reason}", err=True)
        sys.exit(1)

    click.echo("Creating pull request...")
    pr_result = pr_creator.create_pr(
        source_info["repo_url"],
        branch_name,
        crash_context,
        build_result,
        test_result,
        regression_result,
        confidence,
    )

    if pr_result.get("error"):
        click.echo(f"Error: {pr_result['error']}", err=True)
        sys.exit(1)

    final = {
        "fingerprint_id": fingerprint_id,
        "crash_type": crash_type,
        "confidence": confidence,
        "pr_url": pr_result["pr_url"],
        "pr_number": pr_result["pr_number"],
        "build_status": build_result["status"],
        "test_results": {
            "total": test_result.get("total", 0),
            "passed": test_result.get("passed", 0),
            "failed": test_result.get("failed", 0),
        },
        "regression_check": regression_result["status"],
    }

    click.echo("\n" + json.dumps(final, indent=2, default=str))


if __name__ == "__main__":
    main()
