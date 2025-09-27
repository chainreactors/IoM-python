#!/usr/bin/env python3
"""
Malice Network Protocol Buffer Code Generator

Generates Python code from .proto files using betterproto2 and creates
type stub files (.pyi) for better IDE support and static type checking.
"""

import os
import subprocess
import sys
from pathlib import Path


def generate_proto_files(proto_root="../../proto", output_dir="./IoM/proto"):
    """
    Generate Python code from protobuf files using betterproto2.

    Args:
        proto_root: Root directory containing .proto files
        output_dir: Output directory for generated Python code
    """
    proto_root = Path(proto_root).resolve()
    output_dir = Path(output_dir).resolve()

    print(f"Proto root: {proto_root}")
    print(f"Output dir: {output_dir}")

    if not proto_root.is_dir():
        print(f"Error: Proto root directory does not exist: {proto_root}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Find all .proto files
    proto_files = list(proto_root.rglob("*.proto"))
    if not proto_files:
        print(f"Error: No .proto files found in {proto_root}")
        sys.exit(1)

    print(f"Found {len(proto_files)} .proto files")

    # Process directories: client, implant, services
    include_dirs = {"client", "implant", "services"}

    for proto_file in sorted(proto_files):
        rel_path = proto_file.relative_to(proto_root)
        first_dir = str(rel_path.parts[0]) if rel_path.parts else ""

        if first_dir not in include_dirs:
            continue

        print(f"Processing: {rel_path}")

        # Create package directory
        package_dir = output_dir / rel_path.parent
        package_dir.mkdir(parents=True, exist_ok=True)

        # Run betterproto2
        cmd = [
            sys.executable,
            "-m", "grpc_tools.protoc",
            f"-I{proto_root}",
            f"--python_betterproto2_out={output_dir}",
            "--python_betterproto2_opt=pydantic_dataclasses",
            "--python_betterproto2_opt=client_generation=async_sync",
            str(proto_file),
        ]

        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stderr.strip():
            print(f"Warning: {result.stderr.strip()}")

    # Create __init__.py files
    _create_init_files(output_dir)

    print("Proto generation completed")


def generate_stub_files(output_dir="./IoM"):
    """
    Generate .pyi stub files for MaliceClient, MaliceSession, and other components.

    Args:
        output_dir: Output directory containing the IoM package
    """
    output_dir = Path(output_dir).resolve()

    # Check if clientrpc module exists
    clientrpc_path = output_dir / "proto" / "clientrpc" / "__init__.py"
    if not clientrpc_path.exists():
        print("Warning: clientrpc module not found, skipping stub generation")
        return

    print("Generating stub files...")

    # Extract methods from MaliceRpcStub
    methods = _extract_stub_methods(clientrpc_path)
    if not methods:
        print("Warning: No methods found in MaliceRpcStub")
        return

    print(f"Found {len(methods)} methods")

    # Generate client.pyi
    client_stub = _generate_stub_content("IoM.client", "MaliceClient", methods)
    if client_stub:
        client_pyi = output_dir / "client.pyi"
        client_pyi.write_text(client_stub, encoding='utf-8')
        print(f"Generated: {client_pyi}")

    # Generate session.pyi
    session_stub = _generate_stub_content("IoM.session", "MaliceSession", methods)
    if session_stub:
        session_pyi = output_dir / "session.pyi"
        session_pyi.write_text(session_stub, encoding='utf-8')
        print(f"Generated: {session_pyi}")

    # Generate additional stubs for missing components
    _generate_additional_stubs(output_dir, methods)


def _extract_stub_methods(clientrpc_path):
    """Extract method signatures from MaliceRpcStub using AST."""
    import ast

    try:
        source = clientrpc_path.read_text(encoding='utf-8')
        tree = ast.parse(source)
    except Exception as e:
        print(f"AST parsing failed: {e}")
        return []

    methods = []

    class MethodExtractor(ast.NodeVisitor):
        def visit_ClassDef(self, node):
            if node.name == 'MaliceRpcStub':
                for item in node.body:
                    if isinstance(item, ast.AsyncFunctionDef) and not item.name.startswith('_'):
                        method_info = self._extract_method_info(item)
                        if method_info:
                            methods.append(method_info)

        def _extract_method_info(self, node):
            # Build parameter string
            params_parts = []

            # Regular arguments
            for arg in node.args.args:
                if arg.arg == 'self':
                    continue
                type_hint = ast.unparse(arg.annotation) if arg.annotation else "Any"
                params_parts.append(f"{arg.arg}: {type_hint}")

            # Apply defaults
            if node.args.defaults:
                num_defaults = len(node.args.defaults)
                start_index = len(params_parts) - num_defaults
                for i, default in enumerate(node.args.defaults):
                    param_index = start_index + i
                    if 0 <= param_index < len(params_parts):
                        default_value = ast.unparse(default)
                        params_parts[param_index] += f" = {default_value}"

            # Keyword-only arguments
            if node.args.kwonlyargs:
                params_parts.append("*")
                for i, arg in enumerate(node.args.kwonlyargs):
                    type_hint = ast.unparse(arg.annotation) if arg.annotation else "Any"
                    param_str = f"{arg.arg}: {type_hint}"

                    if (i < len(node.args.kw_defaults) and
                        node.args.kw_defaults[i] is not None):
                        default_value = ast.unparse(node.args.kw_defaults[i])
                        param_str += f" = {default_value}"

                    params_parts.append(param_str)

            return {
                'name': node.name,
                'params': ", ".join(params_parts),
                'return_type': ast.unparse(node.returns) if node.returns else "Any"
            }

    extractor = MethodExtractor()
    extractor.visit(tree)
    return methods


def _generate_stub_content(module_name, class_name, methods):
    """Generate stub content using MonkeyType or fallback to manual generation."""
    # Try MonkeyType first
    stub_content = _generate_with_monkeytype(module_name, class_name)

    if not stub_content:
        # Fallback to basic template
        stub_content = _generate_basic_stub(class_name)

    # Inject dynamic methods
    return _inject_methods_into_stub(stub_content, methods, class_name)


def _generate_with_monkeytype(module_name, class_name):
    """Generate stub using MonkeyType."""
    try:
        result = subprocess.run([
            "monkeytype", "stub", module_name
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            content = result.stdout.strip()
            return _extract_class_from_stub(content, class_name)
    except Exception:
        pass

    return ""


def _generate_basic_stub(class_name):
    """Generate basic stub template."""
    if class_name == "MaliceClient":
        return """from typing import Any, Callable, Awaitable
from .config import ClientConfig

class MaliceClient:
    def __init__(self, config: ClientConfig): ...
    @property
    def is_authenticated(self) -> bool: ...
    @property
    def is_connected(self) -> bool: ...
"""
    elif class_name == "MaliceSession":
        return """from typing import Any, Callable, Awaitable
from .client import MaliceClient

class MaliceSession:
    def __init__(self, client: MaliceClient, session_id: str): ...
"""
    return ""


def _extract_class_from_stub(stub_content, class_name):
    """Extract specific class from stub content."""
    lines = stub_content.split('\n')
    result_lines = []
    in_target_class = False
    class_indent = 0

    for line in lines:
        if line.startswith(f'class {class_name}'):
            in_target_class = True
            class_indent = len(line) - len(line.lstrip())
            result_lines.append(line)
        elif in_target_class:
            current_indent = len(line) - len(line.lstrip())
            if line.strip() and current_indent <= class_indent and not line.startswith(' '):
                break
            result_lines.append(line)

    return '\n'.join(result_lines)


def _inject_methods_into_stub(base_stub, methods, class_name):
    """Inject dynamic method signatures into stub."""
    lines = base_stub.split('\n')
    result_lines = []
    in_target_class = False
    injected = False

    for i, line in enumerate(lines):
        result_lines.append(line)

        if line.startswith(f'class {class_name}'):
            in_target_class = True
            continue

        # Inject at end of class
        if in_target_class and not injected:
            is_end = (
                (i == len(lines) - 1) or
                (line.strip() == "" and len(result_lines) > 1 and result_lines[-2].strip().endswith("..."))
            )

            if is_end:
                result_lines.append("")
                result_lines.append("    # Dynamically forwarded methods from MaliceRpcStub")

                # Categorize methods
                categories = _categorize_methods(methods)

                for category_name, category_methods in categories.items():
                    if category_methods:
                        result_lines.append(f"    # {category_name.title()} methods")
                        for method in category_methods:
                            result_lines.append(f"    async def {method['name']}({method['params']}) -> {method['return_type']}: ...")
                            result_lines.append("")

                injected = True
                in_target_class = False

    return '\n'.join(result_lines)


def _categorize_methods(methods):
    """Categorize methods for better organization."""
    categories = {
        'basic': [],
        'task': [],
        'file': [],
        'system': [],
        'execute': [],
        'other': []
    }

    for method in methods:
        name = method['name']
        if name.startswith(('get_basic', 'login', 'get_client', 'get_session', 'get_listener', 'get_audit')):
            categories['basic'].append(method)
        elif name.startswith(('get_task', 'wait_task', 'cancel_task', 'query_task', 'list_task')):
            categories['task'].append(method)
        elif name.startswith(('upload', 'download', 'sync', 'get_file')):
            categories['file'].append(method)
        elif name.startswith(('execute', 'powerpick', 'assembly', 'shellcode', 'bof')):
            categories['execute'].append(method)
        elif name in ['pwd', 'ls', 'cd', 'rm', 'mv', 'cp', 'cat', 'mkdir', 'chmod', 'chown',
                      'ps', 'kill', 'netstat', 'env', 'set_env', 'unset_env', 'whoami', 'info']:
            categories['system'].append(method)
        else:
            categories['other'].append(method)

    return categories


def _generate_additional_stubs(output_dir, methods):
    """Generate stub files for SessionManager and helper functions."""

    # Generate SessionManager stub by extracting from session.py
    session_py = output_dir / "session.py"
    if session_py.exists():
        session_manager_stub = _extract_session_manager_stub(session_py)
        if session_manager_stub:
            # Update session.pyi to include SessionManager
            session_pyi = output_dir / "session.pyi"
            if session_pyi.exists():
                current_content = session_pyi.read_text(encoding='utf-8')
                updated_content = current_content + "\n\n" + session_manager_stub
                session_pyi.write_text(updated_content, encoding='utf-8')
                print(f"Updated: {session_pyi} (added SessionManager)")

    # Generate client helper functions stub
    client_py = output_dir / "client.py"
    if client_py.exists():
        helper_functions_stub = _extract_helper_functions_stub(client_py)
        if helper_functions_stub:
            # Update client.pyi to include helper functions
            client_pyi = output_dir / "client.pyi"
            if client_pyi.exists():
                current_content = client_pyi.read_text(encoding='utf-8')
                updated_content = current_content + "\n\n" + helper_functions_stub
                client_pyi.write_text(updated_content, encoding='utf-8')
                print(f"Updated: {client_pyi} (added helper functions)")


def _extract_session_manager_stub(session_py_path):
    """Extract SessionManager class definition and create stub."""
    import ast

    try:
        source = session_py_path.read_text(encoding='utf-8')
        tree = ast.parse(source)
    except Exception as e:
        print(f"Failed to parse session.py: {e}")
        return ""

    stub_lines = []

    class SessionManagerExtractor(ast.NodeVisitor):
        def visit_ClassDef(self, node):
            if node.name == 'SessionManager':
                stub_lines.append(f"class {node.name}:")

                # Extract methods
                for item in node.body:
                    if isinstance(item, ast.AsyncFunctionDef) and not item.name.startswith('_'):
                        method_stub = self._extract_method_stub(item)
                        if method_stub:
                            stub_lines.append(f"    {method_stub}")
                    elif isinstance(item, ast.FunctionDef) and item.name == '__init__':
                        method_stub = self._extract_method_stub(item)
                        if method_stub:
                            stub_lines.append(f"    {method_stub}")

        def _extract_method_stub(self, node):
            # Build parameter string
            params_parts = []

            # Regular arguments
            for arg in node.args.args:
                type_hint = ast.unparse(arg.annotation) if arg.annotation else "Any"
                params_parts.append(f"{arg.arg}: {type_hint}")

            # Apply defaults
            if node.args.defaults:
                num_defaults = len(node.args.defaults)
                start_index = len(params_parts) - num_defaults
                for i, default in enumerate(node.args.defaults):
                    param_index = start_index + i
                    if 0 <= param_index < len(params_parts):
                        default_value = ast.unparse(default)
                        params_parts[param_index] += f" = {default_value}"

            params_str = ", ".join(params_parts)
            return_type = ast.unparse(node.returns) if node.returns else "Any"

            if isinstance(node, ast.AsyncFunctionDef):
                return f"async def {node.name}({params_str}) -> {return_type}: ..."
            else:
                return f"def {node.name}({params_str}) -> {return_type}: ..."

    extractor = SessionManagerExtractor()
    extractor.visit(tree)

    return "\n".join(stub_lines) if stub_lines else ""


def _extract_helper_functions_stub(client_py_path):
    """Extract helper functions like connect, connect_context."""
    import ast

    try:
        source = client_py_path.read_text(encoding='utf-8')
        tree = ast.parse(source)
    except Exception as e:
        print(f"Failed to parse client.py: {e}")
        return ""

    stub_lines = []
    target_functions = {'connect', 'connect_context'}

    class FunctionExtractor(ast.NodeVisitor):
        def __init__(self):
            self.in_class = False

        def visit_ClassDef(self, node):
            self.in_class = True
            self.generic_visit(node)
            self.in_class = False

        def visit_AsyncFunctionDef(self, node):
            # Only extract module-level functions, not class methods
            if not self.in_class and node.name in target_functions:
                method_stub = self._extract_function_stub(node)
                if method_stub:
                    stub_lines.append(method_stub)

        def visit_FunctionDef(self, node):
            # Only extract module-level functions, not class methods
            if not self.in_class and node.name in target_functions:
                method_stub = self._extract_function_stub(node)
                if method_stub:
                    stub_lines.append(method_stub)

        def _extract_function_stub(self, node):
            # Build parameter string
            params_parts = []

            # Regular arguments
            for arg in node.args.args:
                type_hint = ast.unparse(arg.annotation) if arg.annotation else "Any"
                params_parts.append(f"{arg.arg}: {type_hint}")

            # Apply defaults
            if node.args.defaults:
                num_defaults = len(node.args.defaults)
                start_index = len(params_parts) - num_defaults
                for i, default in enumerate(node.args.defaults):
                    param_index = start_index + i
                    if 0 <= param_index < len(params_parts):
                        default_value = ast.unparse(default)
                        params_parts[param_index] += f" = {default_value}"

            params_str = ", ".join(params_parts)
            return_type = ast.unparse(node.returns) if node.returns else "Any"

            if isinstance(node, ast.AsyncFunctionDef):
                return f"async def {node.name}({params_str}) -> {return_type}: ..."
            else:
                return f"def {node.name}({params_str}) -> {return_type}: ..."

    extractor = FunctionExtractor()
    extractor.visit(tree)

    if stub_lines:
        return "# Helper functions\n" + "\n".join(stub_lines)
    return ""


def _create_init_files(root_dir):
    """Create __init__.py files for all directories."""
    for dir_path in root_dir.rglob("*"):
        if dir_path.is_dir():
            init_file = dir_path / "__init__.py"
            if not init_file.exists():
                init_file.touch()


def main():
    """Main entry point."""
    args = sys.argv[1:]

    if len(args) == 2:
        proto_root, output_dir = args[0], args[1]
        generate_proto_files(proto_root, f"{output_dir}/proto")
        generate_stub_files(output_dir)
    elif len(args) == 0:
        generate_proto_files()
        generate_stub_files()
    else:
        print("""Usage:
    python generate.py [proto_root_dir] [output_dir]

Examples:
    python generate.py                           # Use defaults
    python generate.py ../../proto ./IoM        # Customr paths
""")
        sys.exit(1)


if __name__ == "__main__":
    main()