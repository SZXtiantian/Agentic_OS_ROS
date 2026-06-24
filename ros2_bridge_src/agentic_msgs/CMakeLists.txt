cmake_minimum_required(VERSION 3.8)
project(agentic_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/Task.msg"
  "msg/SkillDescription.msg"
  "msg/WorldObject.msg"
  "msg/RobotState.msg"
  "msg/ArmState.msg"
  "msg/Place.msg"
  "msg/SafetyState.msg"
  "srv/ResolvePlace.srv"
  "srv/GetRobotState.srv"
  "srv/StopRobot.srv"
  "srv/Observe.srv"
  "srv/CapturePhoto.srv"
  "srv/DetectColorBlock.srv"
  "srv/InspectArea.srv"
  "srv/GetArmState.srv"
  "srv/SetGripper.srv"
  "srv/AskHuman.srv"
  "srv/CheckSafety.srv"
  "action/ExecuteSkill.action"
  "action/NavigateToPlace.action"
  "action/MoveArmNamed.action"
  "action/PickColorBlock.action"
  "action/PlaceColorBlock.action"
  DEPENDENCIES geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
