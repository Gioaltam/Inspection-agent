#!/usr/bin/env python
"""Test that both security modules are compatible"""
from backend.app.security import get_password_hash, verify_password
from backend.app.portal_security import hash_password, verify_password as portal_verify

def test_security_compatibility():
    """Test that both security modules produce compatible hashes"""
    test_password = "MySecurePassword123!"

    print("Testing security module compatibility...")
    print("-" * 50)

    # Test the new security.py module
    print("\n1. Testing security.py module:")
    hash_from_security = get_password_hash(test_password)
    print(f"   Hash generated: {hash_from_security[:20]}...")

    # Verify with same module
    verify_same = verify_password(test_password, hash_from_security)
    print(f"   Self-verification: {'PASSED' if verify_same else 'FAILED'}")

    # Verify wrong password
    verify_wrong = verify_password("WrongPassword", hash_from_security)
    print(f"   Wrong password rejection: {'PASSED' if not verify_wrong else 'FAILED'}")

    # Test the portal_security.py module
    print("\n2. Testing portal_security.py module:")
    hash_from_portal = hash_password(test_password)
    print(f"   Hash generated: {hash_from_portal[:20]}...")

    # Verify with same module
    verify_portal_same = portal_verify(test_password, hash_from_portal)
    print(f"   Self-verification: {'PASSED' if verify_portal_same else 'FAILED'}")

    # Cross-module compatibility test
    print("\n3. Cross-module compatibility:")

    # Verify security.py hash with portal_security.py verify
    cross_verify_1 = portal_verify(test_password, hash_from_security)
    print(f"   security.py hash + portal verify: {'PASSED' if cross_verify_1 else 'FAILED'}")

    # Verify portal_security.py hash with security.py verify
    cross_verify_2 = verify_password(test_password, hash_from_portal)
    print(f"   portal hash + security.py verify: {'PASSED' if cross_verify_2 else 'FAILED'}")

    print("\n" + "=" * 50)

    # Overall result
    all_tests_passed = all([
        verify_same,
        not verify_wrong,
        verify_portal_same,
        cross_verify_1,
        cross_verify_2
    ])

    if all_tests_passed:
        print("[RESULT] All security tests PASSED!")
        print("Both modules are fully compatible.")
    else:
        print("[RESULT] Some tests FAILED!")
        print("Check the results above for details.")

    return all_tests_passed

if __name__ == "__main__":
    test_security_compatibility()