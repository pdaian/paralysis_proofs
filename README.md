Paralysis Proofs
================

**WARNING: THESE CONTRACTS HAVE NOT BEEN AUDITED AND SHOULD NOT BE USED TO HOLD SUBSTANTIAL FUNDS EVER**

Paralysis proofs for cryptocurrency (see the [full paper](http://www.initc3.org/files/pp.pdf)'s description).

Paralysis proofs allow for a multisignature account where users can challenge other users' liveness, degrading
the multisig in the event of lost keys, user fatalities, or other problems resulting in the sort of "access control
paralysis" described at a higher level in [our blog post](http://hackingdistributed.com/2018/01/18/paralysis-proofs/).

- **Paralysis.sol** - implementation of a paralysis proof as a Solidity / Ethereum smart contract.
- **paralysis_test.py** - Unit tests of the Ethereum contract.

Running tests
=============

Run `python3.6 paralysis_test.py` in this directory to run all unit tests.
