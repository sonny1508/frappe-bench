import frappe

from frappe.utils import (
    get_time,
)

from datetime import datetime, timedelta

def validate(doc, method):
    """Calculate total working hours and lunch hours"""
    
    # Calculate total lunch hours
    if doc.custom_start_lunch_hour and doc.custom_end_lunch_hour:
        doc.custom_total_lunch_hours = calculate_duration(
            get_time(doc.custom_start_lunch_hour), 
            get_time(doc.custom_end_lunch_hour)
        )
    else:
        doc.custom_total_lunch_hours = None

    # Calculate total working hours
    if doc.custom_start_working_hour and doc.custom_end_working_hour:
        gross_working_hours = calculate_duration(
            get_time(doc.custom_start_working_hour), 
            get_time(doc.custom_end_working_hour)
        )

        # Deduct total lunch hours if it exists
        if doc.custom_total_lunch_hours:
            doc.custom_total_working_hours = gross_working_hours - doc.custom_total_lunch_hours
        else:
            doc.custom_total_working_hours = gross_working_hours
    else:
        doc.custom_total_working_hours = None


def calculate_duration(start_time, end_time):
    """Calculate duration in seconds between two time objects"""
    # Convert time to datetime for calculation
    today = datetime.today().date()
    start_dt = datetime.combine(today, start_time)
    end_dt = datetime.combine(today, end_time)
    
    # Handle case where end time is before start time (crosses midnight)
    if end_dt < start_dt:
        end_dt += timedelta(days=1)
    
    # Return duration in seconds (Frappe duration format)
    duration = (end_dt - start_dt).total_seconds()
    return int(duration)