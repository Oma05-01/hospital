"""
Management command to create staff users.

Usage:
    # Interactive (prompts for all fields):
    python manage.py create_staff

    # Non-interactive (pass all fields as arguments):
    python manage.py create_staff \
        --username jdoe \
        --email john.doe@hospital.com \
        --first_name John \
        --last_name Doe \
        --role doctor \
        --specialty Cardiology \
        --phone 08012345678 \
        --password secret123

Place this file at:
    your_app/management/commands/create_staff.py

Make sure the following directory structure exists (create __init__.py files if needed):
    your_app/
        management/
            __init__.py
            commands/
                __init__.py
                create_staff.py
"""

import getpass
import re

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

# ── Change this import to match your actual app name ──────────────────────────
from staff.models import Staff
# ──────────────────────────────────────────────────────────────────────────────

ROLE_CHOICES = [r[0] for r in Staff.ROLE_CHOICES]   # ['doctor', 'nurse', 'admin']


class Command(BaseCommand):
    help = "Create a new staff user (doctor, nurse, or admin)."

    def add_arguments(self, parser):
        # All arguments are optional — if omitted the command prompts interactively.
        parser.add_argument('--username',   type=str)
        parser.add_argument('--email',      type=str)
        parser.add_argument('--first_name', type=str)
        parser.add_argument('--last_name',  type=str)
        parser.add_argument('--role',       type=str, choices=ROLE_CHOICES)
        parser.add_argument('--specialty',  type=str, default='')
        parser.add_argument('--phone',      type=str)
        parser.add_argument('--password',   type=str,
                            help="Plaintext password. Omit to be prompted securely.")

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _prompt(self, label, default=None, required=True):
        """Prompt the user for input, optionally with a default value."""
        suffix = f" [{default}]" if default else ""
        while True:
            value = input(f"{label}{suffix}: ").strip()
            if not value and default:
                return default
            if value or not required:
                return value
            self.stderr.write(self.style.ERROR(f"  {label} is required."))

    def _prompt_choice(self, label, choices):
        """Prompt for a value restricted to a list of choices."""
        choices_str = "/".join(choices)
        while True:
            value = input(f"{label} ({choices_str}): ").strip().lower()
            if value in choices:
                return value
            self.stderr.write(self.style.ERROR(f"  Choose one of: {choices_str}"))

    def _prompt_password(self):
        """Prompt for a password (hidden) with confirmation."""
        while True:
            pw1 = getpass.getpass("Password: ")
            pw2 = getpass.getpass("Confirm password: ")
            if pw1 != pw2:
                self.stderr.write(self.style.ERROR("  Passwords do not match. Try again."))
                continue
            if len(pw1) < 8:
                self.stderr.write(self.style.ERROR("  Password must be at least 8 characters."))
                continue
            return pw1

    # ── Validation ─────────────────────────────────────────────────────────────

    def _validate_username(self, username):
        if not re.match(r'^[\w.@+-]+$', username):
            raise CommandError(
                "Username may only contain letters, numbers, and @/./+/-/_ characters."
            )
        if User.objects.filter(username=username).exists():
            raise CommandError(f"Username '{username}' is already taken.")
        return username

    def _validate_email(self, email):
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            raise CommandError(f"'{email}' does not look like a valid email address.")
        return email

    # ── Main ───────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("\n── Create Staff User ──\n"))

        # Collect values from args or interactive prompts
        username   = options['username']   or self._prompt("Username")
        first_name = options['first_name'] or self._prompt("First name")
        last_name  = options['last_name']  or self._prompt("Last name")
        email      = options['email']      or self._prompt("Email")
        role       = options['role']       or self._prompt_choice("Role", ROLE_CHOICES)
        phone      = options['phone']      or self._prompt("Phone number")
        specialty  = options['specialty']

        # Specialty is only relevant for doctors
        if role == 'doctor' and not specialty:
            specialty = self._prompt("Specialty", required=False)

        password = options['password'] or self._prompt_password()

        # Validate
        self._validate_username(username)
        self._validate_email(email)

        # Confirm before creating
        self.stdout.write("\n── Summary ──────────────────────────────")
        self.stdout.write(f"  Username   : {username}")
        self.stdout.write(f"  Name       : {first_name} {last_name}")
        self.stdout.write(f"  Email      : {email}")
        self.stdout.write(f"  Role       : {role}")
        if specialty:
            self.stdout.write(f"  Specialty  : {specialty}")
        self.stdout.write(f"  Phone      : {phone}")
        self.stdout.write("─────────────────────────────────────────\n")

        if not options['username']:   # only confirm when running interactively
            confirm = input("Create this staff user? [y/N]: ").strip().lower()
            if confirm != 'y':
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        # Create User
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=True
        )

        # Create Staff profile
        Staff.objects.create(
            user=user,
            role=role,
            specialty=specialty or '',
            phone_number=phone,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Staff user '{username}' ({role}) created successfully."
            )
        )