#!/usr/bin/env python3
"""
Test rozwiązywania zmiennych szablonowych w akcji Lynx Refund.
"""

import asyncio
import sys

sys.path.append('.')

def test_template_variables():
    """Test rozwiązywania zmiennych szablonowych."""
    
    print("🧪 TESTOWANIE ZMIENNYCH SZABLONOWYCH")
    print("="*50)
    
    # Mockowe klasy do testowania
    class MockMessageLogger:
        pass
    
    class MockOrchestrator:
        def __init__(self):
            self._components = {
                'lynx_api': MockLynxComponent()
            }
    
    class MockLynxComponent:
        def get_site_id(self):
            return 123
            
        async def send_refund_request(self, **kwargs):
            return {
                'success': True,
                'transaction_id': kwargs['transaction_id'],
                'reason': kwargs['refund_reason']
            }
            
        def __getattr__(self, name):
            if name == 'send_refund_request':
                return self.send_refund_request
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
    
    # Import akcji
    exec(open('avena_commons/orchestrator/actions/base_action.py').read())
    exec(open('avena_commons/orchestrator/actions/lynx_refund_action.py').read())
    
    # Testy
    async def run_tests():
        action = LynxRefundAction()
        
        # Test 1: Podstawowe zmienne
        print("\n1. Test podstawowych zmiennych:")
        
        context = ActionContext(
            orchestrator=MockOrchestrator(),
            message_logger=MockMessageLogger(),
            trigger_data={
                'transaction_id': 123456,
                'error_message': 'Payment failed',
                'source': 'payment_service',
                'admin_email': 'admin@test.com'
            }
        )
        
        # Test rozwiązywania zmiennych
        test_cases = [
            ("{{ trigger.transaction_id }}", "123456"),
            ("{{ trigger.error_message }}", "Payment failed"),
            ("{{ trigger.source }}", "payment_service"),
            ("{{ trigger.admin_email }}", "admin@test.com"),
            ("Refund for {{ trigger.transaction_id }}: {{ trigger.error_message }}", 
             "Refund for 123456: Payment failed")
        ]
        
        for template, expected in test_cases:
            result = action._resolve_template_variables(template, context)
            status = "✅" if result == expected else "❌"
            print(f"   {status} '{template}' -> '{result}'")
            if result != expected:
                print(f"      Oczekiwano: '{expected}'")
        
        # Test 2: Całościowy test akcji
        print("\n2. Test całej akcji z zmiennymi:")
        
        action_config = {
            "component": "lynx_api",
            "transaction_id": "{{ trigger.transaction_id }}",
            "refund_reason": "Auto refund - {{ trigger.error_message }}",
            "refund_email_list": "{{ trigger.admin_email }}"
        }
        
        try:
            result = await action.execute(action_config, context)
            print(f"   ✅ Akcja wykonana pomyślnie")
            print(f"   📄 Wynik: {result}")
        except Exception as e:
            print(f"   ❌ Błąd akcji: {e}")
        
        # Test 3: Brak zmiennych w trigger_data
        print("\n3. Test z brakującymi zmiennymi:")
        
        context_empty = ActionContext(
            orchestrator=MockOrchestrator(),
            message_logger=MockMessageLogger(),
            trigger_data={}
        )
        
        template = "ID: {{ trigger.transaction_id }}, Error: {{ trigger.error_message }}"
        result = action._resolve_template_variables(template, context_empty)
        print(f"   📝 Template: '{template}'")
        print(f"   📄 Result: '{result}'")
        
        print("\n🎉 Testy zakończone!")
    
    asyncio.run(run_tests())

if __name__ == "__main__":
    test_template_variables()
