# SPDX-License-Identifier: MIT
# Native project startup handshake; no modern provider APIs or source edits.
execute_process(
  COMMAND "${CMAKE_PURIFIER_LEGACY_PYTHON}" "${CMAKE_PURIFIER_LEGACY_DRIVER}"
    identity "${CMAKE_PURIFIER_LEGACY_CONTEXT}"
    "${CMAKE_COMMAND}" "${CMAKE_ROOT}" "${CMAKE_VERSION}" "${CMAKE_PROJECT_NAME}"
    "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_SOURCE_DIR}" "${CMAKE_CURRENT_BINARY_DIR}" "${CMAKE_BINARY_DIR}"
  RESULT_VARIABLE _purifier_identity_status)
if(NOT _purifier_identity_status EQUAL 0)
  message(FATAL_ERROR "cmake-purifier: legacy native SDK/project identity check failed")
endif()
