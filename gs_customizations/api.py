import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def get_login_backgrounds(folder="login_backgrounds"):
    """Get list of background images from a folder in File Manager"""
    
    # Get files from the specified folder
    files = frappe.get_all(
        "File",
        filters={
            "folder": f"Home/{folder}",
            "is_folder": 0,
        },
        fields=["file_url"],
        order_by="creation asc"
    )
    
    # Filter for image files only
    image_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    image_urls = [
        f["file_url"] for f in files 
        if f["file_url"].lower().endswith(image_extensions)
    ]
    
    return image_urls