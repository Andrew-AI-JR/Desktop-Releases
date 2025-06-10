"""
License Validator for LinkedIn Automation Tool
Validates licenses against the backend API and handles local license storage
"""

import requests
import json
import hashlib
import platform
import uuid
import os
from datetime import datetime
from typing import Dict, Optional

class LicenseValidator:
    """Validates and manages license for the LinkedIn automation tool."""
    
    def __init__(self, api_base_url: str = "https://junior-api-915940312680.us-west1.run.app/api/license"):
        self.api_base_url = api_base_url
        self.license_file = ".license"
        self.machine_fingerprint = self._generate_machine_fingerprint()
    
    def _generate_machine_fingerprint(self) -> str:
        """Generate unique machine fingerprint."""
        machine_info = f"{platform.node()}{uuid.getnode()}{platform.machine()}{platform.processor()}"
        return hashlib.sha256(machine_info.encode()).hexdigest()[:16]
    
    def _get_machine_info(self) -> Dict:
        """Get detailed machine information."""
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "hostname": platform.node(),
            "fingerprint": self.machine_fingerprint
        }
    
    def validate_license_online(self, license_key: str) -> Dict:
        """Validate license against the online API."""
        try:
            response = requests.post(
                f"{self.api_base_url}/validate",
                json={
                    "license_key": license_key,
                    "machine_info": self._get_machine_info()
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                return {
                    "valid": True,
                    "data": response.json()
                }
            else:
                error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
                return {
                    "valid": False,
                    "error": error_data.get("detail", f"HTTP {response.status_code}")
                }
                
        except requests.exceptions.RequestException as e:
            return {
                "valid": False,
                "error": f"Network error: {str(e)}"
            }
    
    def activate_license_online(self, license_key: str) -> Dict:
        """Activate license on this machine via the online API."""
        try:
            response = requests.post(
                f"{self.api_base_url}/activate",
                json={
                    "license_key": license_key,
                    "machine_info": self._get_machine_info()
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Save license locally after successful activation
                self._save_license_locally(license_key, result)
                
                return {
                    "valid": True,
                    "activated": True,
                    "data": result
                }
            else:
                error_data = response.json() if response.headers.get('content-type') == 'application/json' else {}
                return {
                    "valid": False,
                    "error": error_data.get("detail", f"HTTP {response.status_code}")
                }
                
        except requests.exceptions.RequestException as e:
            return {
                "valid": False,
                "error": f"Network error: {str(e)}"
            }
    
    def _save_license_locally(self, license_key: str, activation_data: Dict):
        """Save license information locally."""
        license_data = {
            "license_key": license_key,
            "machine_fingerprint": self.machine_fingerprint,
            "activation_date": datetime.now().isoformat(),
            "features": activation_data.get("features", []),
            "expiry_date": activation_data.get("expiry_date"),
            "last_validation": datetime.now().isoformat()
        }
        
        try:
            with open(self.license_file, 'w') as f:
                json.dump(license_data, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save license locally: {e}")
    
    def load_local_license(self) -> Optional[Dict]:
        """Load license from local file."""
        if not os.path.exists(self.license_file):
            return None
        
        try:
            with open(self.license_file, 'r') as f:
                license_data = json.load(f)
            
            # Verify machine fingerprint
            if license_data.get("machine_fingerprint") != self.machine_fingerprint:
                return None
            
            return license_data
            
        except Exception as e:
            print(f"Error loading local license: {e}")
            return None
    
    def is_license_expired(self, license_data: Dict) -> bool:
        """Check if license is expired."""
        try:
            expiry_date = datetime.fromisoformat(license_data["expiry_date"].replace('Z', '+00:00'))
            return datetime.now() > expiry_date.replace(tzinfo=None)
        except:
            return True
    
    def validate_license(self, license_key: str = None, force_online: bool = False) -> Dict:
        """
        Validate license with fallback strategy:
        1. Try online validation first
        2. Fall back to local validation if offline
        """
        
        # If no license key provided, try to load from local file
        if not license_key:
            local_license = self.load_local_license()
            if local_license:
                license_key = local_license["license_key"]
            else:
                return {
                    "valid": False,
                    "error": "No license found. Please enter your license key."
                }
        
        # Try online validation first (unless we have a recent local validation)
        if force_online or self._should_validate_online():
            online_result = self.validate_license_online(license_key)
            if online_result["valid"]:
                # Update local license with latest info
                self._save_license_locally(license_key, online_result["data"])
                return online_result
            
            # If online validation fails, try local validation
            print(f"Online validation failed: {online_result['error']}")
        
        # Fall back to local validation
        local_license = self.load_local_license()
        if local_license:
            if self.is_license_expired(local_license):
                return {
                    "valid": False,
                    "error": "License has expired. Please renew your subscription."
                }
            
            return {
                "valid": True,
                "data": {
                    "features": local_license.get("features", []),
                    "expiry_date": local_license.get("expiry_date"),
                    "offline_mode": True
                }
            }
        
        return {
            "valid": False,
            "error": "License validation failed. Please check your internet connection and license key."
        }
    
    def _should_validate_online(self) -> bool:
        """Determine if we should validate online based on last validation time."""
        local_license = self.load_local_license()
        if not local_license:
            return True
        
        try:
            last_validation = datetime.fromisoformat(local_license.get("last_validation", ""))
            # Validate online if last validation was more than 24 hours ago
            return (datetime.now() - last_validation).total_seconds() > 86400
        except:
            return True
    
    def activate_license(self, license_key: str) -> Dict:
        """Activate a license key."""
        return self.activate_license_online(license_key)
    
    def get_license_status(self) -> Dict:
        """Get current license status."""
        local_license = self.load_local_license()
        if not local_license:
            return {
                "status": "no_license",
                "message": "No license found"
            }
        
        if self.is_license_expired(local_license):
            return {
                "status": "expired",
                "message": "License has expired",
                "expiry_date": local_license.get("expiry_date")
            }
        
        return {
            "status": "active",
            "message": "License is active",
            "features": local_license.get("features", []),
            "expiry_date": local_license.get("expiry_date"),
            "machine_fingerprint": self.machine_fingerprint
        }
    
    def remove_license(self):
        """Remove local license file."""
        try:
            if os.path.exists(self.license_file):
                os.remove(self.license_file)
                return True
        except Exception as e:
            print(f"Error removing license: {e}")
        return False 