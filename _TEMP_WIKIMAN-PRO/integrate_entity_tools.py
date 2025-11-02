#!/usr/bin/env python3
"""
Integration script to add entity search tools to WikiMan
Run this to patch wikiman.py with entity search capabilities
"""

import sys
from pathlib import Path

def create_integration_patch():
    """Create patch to integrate entity tools into wikiman.py"""
    
    patch_content = '''
# ============= ENTITY TOOLS INTEGRATION PATCH =============
# Add this to wikiman.py to enable entity search capabilities

# 1. Add import at the top of the file (after other imports):
from wikiman_entity_tools import get_entity_tools, get_entity_tool_handlers

# 2. Add entity tools to TOOLS list (after line 716 where TOOLS is defined):
TOOLS.extend(get_entity_tools())

# 3. Add entity tool handlers to the execution chain (in the chat function around line 2235):
# Find the section with all the elif statements for tool execution and add:

entity_handlers = get_entity_tool_handlers()

# Then in the tool execution section, add these elif statements:
elif name == "entity_email_search": 
    result = entity_handlers["entity_email_search"](args.get("email", ""))
elif name == "entity_username_search": 
    result = entity_handlers["entity_username_search"](args.get("username", ""))
elif name == "entity_phone_search": 
    result = entity_handlers["entity_phone_search"](args.get("phone", ""))
elif name == "entity_password_search": 
    result = entity_handlers["entity_password_search"](args.get("password", ""))
elif name == "entity_domain_whois": 
    result = entity_handlers["entity_domain_whois"](args.get("domain", ""))
elif name == "entity_person_search": 
    result = entity_handlers["entity_person_search"](
        args.get("name", ""), 
        args.get("email", None)
    )
elif name == "entity_recursive_expand": 
    result = entity_handlers["entity_recursive_expand"](
        args.get("entity_type", ""),
        args.get("entity_value", ""),
        args.get("max_depth", 2)
    )

# ============= END OF PATCH =============
'''
    
    print(patch_content)
    
    # Save patch file
    patch_file = Path("wikiman_entity_tools.patch")
    with open(patch_file, 'w') as f:
        f.write(patch_content)
    
    print(f"\n✅ Patch saved to: {patch_file}")
    print("\nTo apply manually, add the code sections shown above to wikiman.py")
    print("\nOr use the automated integration below:")
    

def automated_integration():
    """Automatically integrate entity tools into wikiman.py"""
    
    wikiman_path = Path("wikiman.py")
    
    if not wikiman_path.exists():
        print("❌ wikiman.py not found in current directory")
        return False
    
    # Read current wikiman.py
    with open(wikiman_path, 'r') as f:
        lines = f.readlines()
    
    # Check if already integrated
    if any("wikiman_entity_tools" in line for line in lines):
        print("✅ Entity tools already integrated into wikiman.py")
        return True
    
    print("🔧 Integrating entity tools into wikiman.py...")
    
    # 1. Add import after other imports
    import_added = False
    for i, line in enumerate(lines):
        if line.startswith("import") or line.startswith("from"):
            continue
        elif not import_added and i > 10:  # After imports section
            lines.insert(i, "\n# Entity search tools integration\n")
            lines.insert(i+1, "from wikiman_entity_tools import get_entity_tools, get_entity_tool_handlers\n")
            import_added = True
            break
    
    # 2. Extend TOOLS list
    tools_extended = False
    for i, line in enumerate(lines):
        if line.strip() == "]" and i > 0 and "TOOLS = [" in "".join(lines[max(0,i-30):i]):
            # Found end of TOOLS list
            lines[i] = "]\n\n# Add entity search tools\nTOOLS.extend(get_entity_tools())\n"
            tools_extended = True
            break
    
    # 3. Add handlers to execution chain
    handlers_added = False
    entity_handler_code = '''
                # Entity search tools
                entity_handlers = get_entity_tool_handlers()
                if name in entity_handlers:
                    if name == "entity_person_search":
                        result = entity_handlers[name](args.get("name", ""), args.get("email", None))
                    elif name == "entity_recursive_expand":
                        result = entity_handlers[name](
                            args.get("entity_type", ""),
                            args.get("entity_value", ""),
                            args.get("max_depth", 2)
                        )
                    else:
                        # Single parameter tools
                        param_map = {
                            "entity_email_search": "email",
                            "entity_username_search": "username",
                            "entity_phone_search": "phone",
                            "entity_password_search": "password",
                            "entity_domain_whois": "domain"
                        }
                        param = param_map.get(name, list(args.keys())[0] if args else "")
                        result = entity_handlers[name](args.get(param, ""))
'''
    
    for i, line in enumerate(lines):
        if "elif name==" in line and "aleph_ai_agent" in line:
            # Add after the last tool handler
            lines.insert(i+1, entity_handler_code)
            handlers_added = True
            break
    
    if import_added and tools_extended and handlers_added:
        # Write back
        with open(wikiman_path, 'w') as f:
            f.writelines(lines)
        print("✅ Successfully integrated entity tools into wikiman.py")
        return True
    else:
        print(f"⚠️ Partial integration: import={import_added}, tools={tools_extended}, handlers={handlers_added}")
        print("Please review wikiman.py and complete integration manually")
        return False


def test_integration():
    """Test that entity tools are working"""
    print("\n" + "="*60)
    print("TESTING ENTITY TOOLS INTEGRATION")
    print("="*60)
    
    try:
        from wikiman_entity_tools import get_entity_tools, get_entity_tool_handlers
        
        tools = get_entity_tools()
        handlers = get_entity_tool_handlers()
        
        print(f"\n✅ Successfully loaded {len(tools)} entity tools:")
        for tool in tools:
            name = tool["function"]["name"]
            print(f"   - {name}")
        
        print(f"\n✅ Successfully loaded {len(handlers)} tool handlers")
        
        # Test a simple tool call
        print("\n🧪 Testing email search tool...")
        test_result = handlers["entity_email_search"]("test@example.com")
        if "ok" in test_result:
            print("✅ Email search tool executed successfully")
        else:
            print("⚠️ Email search returned unexpected format")
        
        print("\n✅ All entity tools are ready for use in WikiMan!")
        print("\n📝 Usage examples:")
        print('   wikiman> Search for email john@example.com in breaches')
        print('   wikiman> Lookup WHOIS for domain example.com')
        print('   wikiman> Find all entities connected to username johndoe123')
        print('   wikiman> Search for person "John Smith" with recursive expansion')
        
    except ImportError as e:
        print(f"❌ Failed to import entity tools: {e}")
        print("Make sure wikiman_entity_tools.py is in the same directory")
    except Exception as e:
        print(f"❌ Error testing tools: {e}")


def main():
    """Main integration script"""
    print("WikiMan Entity Tools Integration Script")
    print("=" * 60)
    
    # Show patch instructions
    create_integration_patch()
    
    # Ask for automated integration
    print("\n" + "="*60)
    response = input("\nWould you like to automatically integrate entity tools into wikiman.py? (y/n): ")
    
    if response.lower() == 'y':
        if automated_integration():
            test_integration()
        else:
            print("\n⚠️ Automated integration incomplete. Please apply the patch manually.")
    else:
        print("\n📝 Please apply the patch manually using the instructions above")
        print("Then run: python3 integrate_entity_tools.py test")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_integration()
    else:
        main()