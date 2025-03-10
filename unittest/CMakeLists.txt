include(GTest)

# check if we can run the compiled executable and whether it prints
# the LAMMPS version header in the output for an empty input
file(WRITE ${CMAKE_CURRENT_BINARY_DIR}/in.empty "")
add_test(NAME RunLammps
         COMMAND $<TARGET_FILE:lmp> -log none -echo none -in in.empty
         WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
set_tests_properties(RunLammps PROPERTIES
        PASS_REGULAR_EXPRESSION "^LAMMPS \\([0-9]+ [A-Za-z]+ 2[0-9][0-9][0-9]\\)")

if(BUILD_MPI)
  function(add_mpi_test)
    set(MPI_TEST_NUM_PROCS 1)
    set(MPI_TEST_WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
    cmake_parse_arguments(MPI_TEST "" "NAME;NUM_PROCS;WORKING_DIRECTORY" "COMMAND" ${ARGN})
    list(GET MPI_TEST_COMMAND 0 EXECUTABLE)
    list(REMOVE_AT MPI_TEST_COMMAND 0)
    set(ARGS ${MPI_TEST_COMMAND})
    add_test(NAME ${MPI_TEST_NAME}
             WORKING_DIRECTORY ${MPI_TEST_WORKING_DIRECTORY}
             COMMAND ${MPIEXEC_EXECUTABLE} ${MPIEXEC_NUMPROC_FLAG} ${MPI_TEST_NUM_PROCS} ${MPIEXEC_PREFLAGS}
                     ${EXECUTABLE} ${MPIEXEC_POSTFLAGS} ${ARGS}
    )
  endfunction()
endif()

add_subdirectory(utils)
add_subdirectory(formats)
add_subdirectory(commands)
add_subdirectory(c-library)
add_subdirectory(cplusplus)
add_subdirectory(fortran)
add_subdirectory(python)
add_subdirectory(tools)
add_subdirectory(force-styles)

find_package(ClangFormat 8.0)

if(ClangFormat_FOUND)
  set(UNITTEST_SOURCES)
  file(GLOB_RECURSE UNITTEST_SOURCES *.cpp *.h)
  add_custom_target(format-tests
    COMMAND ${ClangFormat_EXECUTABLE} --verbose -i -style=file ${UNITTEST_SOURCES}
    DEPENDS ${UNITTEST_SOURCES})
endif()
