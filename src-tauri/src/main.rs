// Prevents additional console window on Windows, do not remove!
#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

fn main() {
    ems_simulate::run()
}
