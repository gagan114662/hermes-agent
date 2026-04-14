#!/usr/bin/env python3
"""Run a single employee shift. Called by cron.

Usage
-----
    # Run one employee:
    python -m harness.run_employee_shift ada

    # Run all employees sequentially:
    python -m harness.run_employee_shift all

Cron example (run Ada's shift every weekday at 9am):
    0 9 * * 1-5 cd /path/to/hermes-agent && python -m harness.run_employee_shift ada
"""
import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _run_one(name: str) -> dict:
    """Run a single employee shift and return the result dict."""
    from harness.employee_loop import EmployeeLoop
    loop = EmployeeLoop(name)
    return asyncio.run(loop.run_shift())


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "all"

    if name == "all":
        from harness.employee import Employee
        employees = Employee.list_all()
        if not employees:
            logger.warning("No employees found in ~/.hermes/employees/")
            return

        logger.info("Running shifts for %d employees", len(employees))
        for emp in employees:
            try:
                result = _run_one(emp.name)
                print(f"{emp.name}: {json.dumps(result, indent=2)}")
            except FileNotFoundError as exc:
                logger.error("Employee config missing for %s: %s", emp.name, exc)
            except Exception as exc:
                logger.exception("Shift failed for %s: %s", emp.name, exc)
    else:
        try:
            result = _run_one(name)
            print(json.dumps(result, indent=2))
        except FileNotFoundError as exc:
            logger.error("Employee not found: %s", exc)
            sys.exit(1)
        except Exception as exc:
            logger.exception("Shift failed for %s: %s", name, exc)
            sys.exit(1)


if __name__ == "__main__":
    main()
