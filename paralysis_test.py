# Requires Python 3.6, Solidity, and pyethereum dependencies
# Author: Philip Daian

import unittest, time
from ethereum.tools import tester
import ethereum.utils as utils
import ethereum.abi as abi

class TestParalysis(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestParalysis, cls).setUpClass()
        # Initialize tester, contract and expose relevant objects
        cls.t = tester
        cls.s = cls.t.Chain()

        cls.s.head_state.gas_limit = 10**80

    def setUp(self):
        self.s.mine()
        super().setUp()

    def get_contract(self, mu1, mu2, delta, keyholders):
        """ Create a paralysis proof contract object with the given parameters """
        contract_file = open('Paralysis.sol')
        contract_code = contract_file.read()
        contract_file.close()
        return self.s.contract(contract_code, language='solidity', args=[mu1, mu2, delta, keyholders])

    def paralyze(self, to_paralyze, paralyzed_by, c, offset=0):
        """ Utility method to paralyze a user on contract 'c' """
        accusation_timestamp = self.s.head_state.timestamp
        delta = c.delta()
        expiry = c.accuse(to_paralyze, sender=paralyzed_by)
        self.assertTrue(expiry == accusation_timestamp + delta) # check that expiry was correctly calculated
        self.s.mine()
        self.s.block.header.timestamp = expiry + offset
        self.s.mine(coinbase=self.t.a0) # if offset is 0, mine the last block that could possibly have contained a response
        # (if offset >= 0, to_paralyze is now confirmed paralyzed)

    def assert_tx_failed(self, function_to_test,
                     exception=tester.TransactionFailed):
        """ Ensure that transaction fails, reverting state
        (to prevent gas exhaustion) """
        initial_state = self.s.snapshot()
        self.assertRaises(exception, function_to_test)
        self.s.revert(initial_state)

    def test_is_active_keyholder(self):
        c = self.get_contract(2, 3, 8000, [self.t.a0, self.t.a1, self.t.a2])
        # Test that all valid keyholders are indeed keyholders
        self.assertTrue(c.is_active_keyholder(self.t.a0))
        self.assertTrue(c.is_active_keyholder(self.t.a1))
        self.assertTrue(c.is_active_keyholder(self.t.a2))

        # Test that non-keyholders are not keyholders
        self.assertFalse(c.is_active_keyholder(self.t.a3))
        self.assertFalse(c.is_active_keyholder(0))

        # Paralyze a user and make sure they are no longer a keyholder
        self.paralyze(self.t.a0, self.t.k1, c)
        self.assertFalse(c.is_active_keyholder(self.t.a0))
        # (make sure other users are still holders)
        self.assertTrue(c.is_active_keyholder(self.t.a1))
        self.assertTrue(c.is_active_keyholder(self.t.a2))

    def test_paralysis_boundaries(self):
        c = self.get_contract(2, 3, 8000, [self.t.a0, self.t.a1, self.t.a2])
        # Paralyze a user and make sure they are no longer a keyholder (as above)
        self.paralyze(self.t.a0, self.t.k1, c)
        self.assertFalse(c.is_active_keyholder(self.t.a0))
        # (make sure other users are still holders)
        self.assertTrue(c.is_active_keyholder(self.t.a1))
        self.assertTrue(c.is_active_keyholder(self.t.a2))
        # Paralyze another user, but this time stop 1 block short of deadline
        self.paralyze(self.t.a2, self.t.k1, c, offset=-1)
        # ensure that all users are still keyholders
        self.assertTrue(c.is_active_keyholder(self.t.a1))
        self.assertTrue(c.is_active_keyholder(self.t.a2))
        # mine one block
        self.s.mine()
        # now, a2 should be removed
        self.assertFalse(c.is_active_keyholder(self.t.a2))

    def test_paralysis_response(self):
        # As in above test, paralyze a2 and stop 1 block short
        c = self.get_contract(2, 3, 8000, [self.t.a0, self.t.a1, self.t.a2])
        self.paralyze(self.t.a2, self.t.k1, c, offset=-1)
        # ensure that all users are still keyholders
        self.assertTrue(c.is_active_keyholder(self.t.a1))
        self.assertTrue(c.is_active_keyholder(self.t.a2))
        # a2 responds to proof
        c.respond(sender=self.t.k2)
        # mine one block
        self.s.mine()
        # unlike above, a2 should be active
        self.assertTrue(c.is_active_keyholder(self.t.a2))

    def test_noparalysis_withdraw_2_of_3(self):
        # test deposit
        c = self.get_contract(2, 3, 8000, [self.t.a0, self.t.a1, self.t.a2])
        self.s.tx(sender=self.t.k0, to=c.address, value=10)
        self.s.mine()
        initial_a0_balance = self.s.head_state.get_balance(self.t.a0)
        self.assertEqual(self.s.head_state.get_balance(c.address), 10)

        # test that 2/3 keyholders can withdraw
        self.assertTrue(c.is_active_keyholder(self.t.a1))
        proposal_id = c.createSpendProposal(self.t.a0, 5, sender=self.t.k1)
        self.assertEqual(proposal_id, 0)
        self.assertEqual(initial_a0_balance, self.s.head_state.get_balance(self.t.a0)) # not enough sigs, no withdraw
        c.spend(proposal_id, sender=self.t.k1)                                         # make sure repeated sig has no impact
        self.assertEqual(initial_a0_balance, self.s.head_state.get_balance(self.t.a0)) # still not enough sigs, no withdraw
        c.spend(proposal_id, sender=self.t.k2)
        self.assertEqual(initial_a0_balance + 5, self.s.head_state.get_balance(self.t.a0))

        # test that boundary 2/3 keyholders can withdraw second proposal
        self.s.mine()
        initial_a1_balance = self.s.head_state.get_balance(self.t.a1)
        self.assertEqual(self.s.head_state.get_balance(c.address), 5)
        proposal_id = c.createSpendProposal(self.t.a1, 5, sender=self.t.k0)
        self.assertEqual(proposal_id, 1)
        self.assertEqual(initial_a1_balance, self.s.head_state.get_balance(self.t.a1)) # not enough sigs, no withdraw
        self.assert_tx_failed(lambda: c.spend(proposal_id, sender=self.t.k3))
        self.assertEqual(initial_a1_balance, self.s.head_state.get_balance(self.t.a1)) # invalid sig, no withdraw
        c.spend(proposal_id, sender=self.t.k2)
        self.assertEqual(initial_a1_balance + 5, self.s.head_state.get_balance(self.t.a1))


    def test_noparalysis_withdraw_2_of_2(self):
        # same as 2-of-3 test, but with an m-of-m multisig
        c = self.get_contract(1, 1, 8000, [self.t.a0, self.t.a1])
        self.s.tx(sender=self.t.k0, to=c.address, value=10)
        self.s.mine()
        initial_a0_balance = self.s.head_state.get_balance(self.t.a0)
        self.assertEqual(self.s.head_state.get_balance(c.address), 10)

        # test that 2/2 keyholders can withdraw
        self.assertTrue(c.is_active_keyholder(self.t.a1))
        proposal_id = c.createSpendProposal(self.t.a0, 5, sender=self.t.k1)
        self.assertEqual(proposal_id, 0)
        self.assertEqual(initial_a0_balance, self.s.head_state.get_balance(self.t.a0)) # not enough sigs, no withdraw
        c.spend(proposal_id, sender=self.t.k1)                                         # make sure repeated sig has no impact
        self.assertEqual(initial_a0_balance, self.s.head_state.get_balance(self.t.a0)) # still not enough sigs, no withdraw
        c.spend(proposal_id, sender=self.t.k0)
        self.assertEqual(initial_a0_balance + 5, self.s.head_state.get_balance(self.t.a0))

    def test_paralysis_2_of_4_to_1_of_2(self):
        c = self.get_contract(2, 4, 8000, [self.t.a0, self.t.a1, self.t.a2, self.t.a3])
        self.s.tx(sender=self.t.k0, to=c.address, value=10)
        self.s.mine()
        initial_a0_balance = self.s.head_state.get_balance(self.t.a0)
        self.assertEqual(self.s.head_state.get_balance(c.address), 10)

        # test that 2/4 keyholders can withdraw
        self.assertTrue(c.is_active_keyholder(self.t.a1))
        proposal_id = c.createSpendProposal(self.t.a0, 5, sender=self.t.k1)
        self.assertEqual(proposal_id, 0)
        self.assertEqual(initial_a0_balance, self.s.head_state.get_balance(self.t.a0)) # not enough sigs, no withdraw
        c.spend(proposal_id, sender=self.t.k1)                                         # make sure repeated sig has no impact
        self.assertEqual(initial_a0_balance, self.s.head_state.get_balance(self.t.a0)) # still not enough sigs, no withdraw
        c.spend(proposal_id, sender=self.t.k2)
        self.assertEqual(initial_a0_balance + 5, self.s.head_state.get_balance(self.t.a0))

        # test that 1/2 keyholders can withdraw second proposal after paralysis
        self.s.mine()
        initial_a1_balance = self.s.head_state.get_balance(self.t.a1)
        self.assertEqual(self.s.head_state.get_balance(c.address), 5)
        proposal_id = c.createSpendProposal(self.t.a1, 5, sender=self.t.k3)
        self.assertEqual(proposal_id, 1)
        # two users accused; neither respond
        self.paralyze(self.t.a0, self.t.k1, c)
        self.paralyze(self.t.a1, self.t.k2, c)
        self.assertEqual(initial_a1_balance, self.s.head_state.get_balance(self.t.a1)) # not enough sigs, no withdraw
        self.assert_tx_failed(lambda: c.spend(proposal_id, sender=self.t.k0))
        self.assert_tx_failed(lambda: c.spend(proposal_id, sender=self.t.k1))
        self.assertEqual(initial_a1_balance, self.s.head_state.get_balance(self.t.a1)) # invalid sig, no withdraw
        c.spend(proposal_id, sender=self.t.k2)
        self.assertEqual(initial_a1_balance + 5, self.s.head_state.get_balance(self.t.a1)) # with signatures from 3 & 2, withdraw goes thru

    def test_paralysis_2_of_4_to_1_of_1(self):
        # same as 2 of 4 to 1 of 2, but ensure that after 3 paralyses any one user can spend
        c = self.get_contract(2, 4, 8000, [self.t.a0, self.t.a1, self.t.a2, self.t.a3])
        self.s.tx(sender=self.t.k0, to=c.address, value=10)
        self.s.mine()
        initial_a0_balance = self.s.head_state.get_balance(self.t.a0)
        self.assertEqual(self.s.head_state.get_balance(c.address), 10)

        # test that 2/4 keyholders can withdraw
        self.assertTrue(c.is_active_keyholder(self.t.a1))
        proposal_id = c.createSpendProposal(self.t.a0, 5, sender=self.t.k1)
        self.assertEqual(proposal_id, 0)
        self.assertEqual(initial_a0_balance, self.s.head_state.get_balance(self.t.a0)) # not enough sigs, no withdraw
        c.spend(proposal_id, sender=self.t.k1)                                         # make sure repeated sig has no impact
        self.assertEqual(initial_a0_balance, self.s.head_state.get_balance(self.t.a0)) # still not enough sigs, no withdraw
        c.spend(proposal_id, sender=self.t.k2)
        self.assertEqual(initial_a0_balance + 5, self.s.head_state.get_balance(self.t.a0))

        # test that 1/2 keyholders can withdraw second proposal after paralysis
        self.s.mine()
        initial_a1_balance = self.s.head_state.get_balance(self.t.a1)
        self.assertEqual(self.s.head_state.get_balance(c.address), 5)
        proposal_id = c.createSpendProposal(self.t.a1, 5, sender=self.t.k0)
        self.assertEqual(proposal_id, 1)
        # three users accused; none respond
        self.paralyze(self.t.a0, self.t.k1, c)
        self.paralyze(self.t.a1, self.t.k2, c)
        self.paralyze(self.t.a3, self.t.k2, c)
        self.assertEqual(initial_a1_balance, self.s.head_state.get_balance(self.t.a1)) # not enough sigs, no withdraw
        self.s.mine()
        self.assert_tx_failed(lambda: c.spend(proposal_id, sender=self.t.k0))
        self.assert_tx_failed(lambda: c.spend(proposal_id, sender=self.t.k1))
        self.assert_tx_failed(lambda: c.spend(proposal_id, sender=self.t.k3))
        self.assertEqual(initial_a1_balance, self.s.head_state.get_balance(self.t.a1)) # invalid sigs, no withdraw
        c.spend(proposal_id, sender=self.t.k2)
        self.assertEqual(initial_a1_balance + 5, self.s.head_state.get_balance(self.t.a1))

    def test_constructor_params_validity(self):
        # TODO
        pass

    def test_access_control(self):
        # TODO
        pass

    def test_modifier(self):
        # TODO
        pass

if __name__ == '__main__':
    unittest.main()


