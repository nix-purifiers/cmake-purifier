cmake_minimum_required(VERSION 3.20)
project(schema_bundle VERSION 1.0.0 LANGUAGES NONE)
install(DIRECTORY schemas/ DESTINATION share/schemas)
install(FILES private.txt DESTINATION share)
