import frappe

def boot_session(bootinfo):
    bootinfo.manager_roles = frappe.conf.get("manager_roles")