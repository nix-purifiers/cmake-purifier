cmake_minimum_required(VERSION 3.20)
project(capnproto_schema VERSION 1.0.0 LANGUAGES NONE)
install(DIRECTORY schemas/ DESTINATION share/schemas)
