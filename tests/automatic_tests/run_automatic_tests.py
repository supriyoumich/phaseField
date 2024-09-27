import subprocess
import shutil
import glob
import os
import datetime
import time
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed


def remove_file(file):
    """Remove a file if it exists

    Args:
            file (string): Path to file
    """
    if os.path.exists(file):
        os.remove(file)


def write_to_file(file, text):
    """Write text to file

    Args:
        file (string): Path to file
        text (string): Text to write in file
    """
    with open(file, "a") as text_file:
        text_file.write(text)


def compile_and_run_unit_tests():
    # Remove old files if they exist
    remove_file("main")
    remove_file("CMakeCache.txt")
    remove_file("unit_test_results.txt")

    # Compile and run
    subprocess.call(
        ["cmake", "."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    subprocess.call(["make"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.call(
        ["mpirun", "-n", "1", "./main"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    with open("unit_test_results.txt", "r") as result_file:
        return result_file.read().splitlines()


def compile_and_run_simulation(application_path):
    # Navigate to test application directory
    os.chdir(application_path)

    # Remove old files
    remove_file("main")
    remove_file("CMakeCache.txt")
    remove_file("integratedFields.txt")
    for solution_file in glob.glob("solution-*.vtu"):
        os.remove(solution_file)

    # Compile application
    subprocess.call(
        ["cmake", "."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    subprocess.call(
        ["make", "release"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    # Print successful compilation to screen
    print("Compiling complete, running the regression test...")
    sys.stdout.flush()

    # Run application with timer
    start = time.time()
    subprocess.call(
        ["mpirun", "-n", "1", "./main"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    end = time.time()

    return end - start


def run_regression_test(application, new_gold_standard, test_dir):
    # Move to the application directory
    application_path = os.path.join(test_dir, application)

    # Run the simulation and move the results to the test directory
    test_time = compile_and_run_simulation(application_path)

    # Compare the result against the gold standard, if it exists
    if new_gold_standard:
        shutil.move("integratedFields.txt", "gold_integratedFields.txt")
        test_passed = True
    else:
        # Read the gold standard free energies
        with open("gold_integratedFields.txt", "r") as gold_standard_file:
            gold_energy = gold_standard_file.readlines()

        split_last_line = gold_energy[-1].split()
        for index, entry in enumerate(split_last_line):
            if entry == "f_tot":
                gold_last_energy = split_last_line[index + 1]

        # Read the test free energies
        with open("integratedFields.txt", "r") as test_file:
            test_energy = test_file.readlines()

        split_last_line = test_energy[-1].split()
        for index, entry in enumerate(split_last_line):
            if entry == "f_tot":
                last_energy = split_last_line[index + 1]

        # Compare the relative difference. If under a certain threshold pass
        rel_diff = abs(
            (float(gold_last_energy) - float(last_energy)) / float(gold_last_energy)
        )
        test_passed = rel_diff < 1.0e-9

    # Determine test result
    test_result = (
        "New Gold Standard"
        if test_passed and new_gold_standard
        else "Pass"
        if test_passed
        else "Fail"
    )

    # Print the results to the screen
    print(
        f"Regression Test: {application}\n"
        f"Result: {test_result}\n"
        f"Time taken: {test_time}\n"
    )
    sys.stdout.flush()

    # Write the results to a file
    test_result_file = os.path.join(test_dir, "test_results.txt")
    write_to_file(
        test_result_file,
        f"Application: {application}\n"
        f"Result: {test_result}\n"
        f"Time: {test_time}\n \n",
    )

    return test_passed, test_time


def run_regression_tests_in_parallel(application_list, gold_standard_list, test_dir):
    regression_test_counter = 0
    regression_tests_passed = 0

    with ProcessPoolExecutor(max_workers=1) as executor:
        futures = [
            executor.submit(run_regression_test, application, gold_standard, test_dir)
            for application, gold_standard in zip(application_list, gold_standard_list)
        ]

        for future in as_completed(futures):
            test_passed, test_time = future.result()
            regression_tests_passed += int(test_passed)
            regression_test_counter += 1

    return regression_tests_passed, regression_test_counter


# Initialize
pwd = os.path.dirname(os.path.realpath(__file__))
test_result_file = os.path.join(pwd, "test_results.txt")

now = datetime.datetime.now()
os.chdir("../unit_tests/")
unit_test_results = compile_and_run_unit_tests()
unit_tests_passed = unit_test_results[0]
unit_test_counter = unit_test_results[1]

write_to_file(
    test_result_file,
    "--------------------------------------------------------- \n"
    "Unit test on " + now.strftime("%Y-%m-%d %H:%M") + "\n"
    "--------------------------------------------------------- \n"
    f"Unit Tests Passed: {unit_tests_passed}/{unit_test_counter}\n",
)


write_to_file(
    test_result_file,
    "--------------------------------------------------------- \n"
    "Regression test on " + now.strftime("%Y-%m-%d %H:%M") + "\n"
    "--------------------------------------------------------- \n",
)

# List of applications
applicationList = [
    "allenCahn",
    "cahnHilliard",
    "CHAC_anisotropyRegularized",
    "coupledCahnHilliardAllenCahn",
    "precipitateEvolution",
]
getNewGoldStandardList = [False, False, False, False, False]

regression_tests_passed, regression_test_counter = run_regression_tests_in_parallel(
    applicationList, getNewGoldStandardList, pwd
)

os.chdir(pwd)
# Output the overall test results
write_to_file(
    test_result_file,
    f"Tests Passed: {regression_tests_passed}/{regression_test_counter}\n"
    "--------------------------------------------------------- \n",
)

# Print overall results
print(f"Unit Tests Passed: {unit_tests_passed}/{unit_test_counter}\n")
print(f"Regression Tests Passed: {regression_tests_passed}/{regression_test_counter}\n")

# Set exit code
if (regression_tests_passed < regression_test_counter) or (
    unit_tests_passed < unit_test_counter
):
    sys.exit(1)
else:
    sys.exit(0)
