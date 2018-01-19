// WARNING: DO NOT SEND ERC20, ERC721, etc. TOKENS TO THIS CONTRACT: THEY *WILL* BE STUCK
// @TODO - SafeMath / overflow issues
// @TODO - Fix Solidity style guide issues
// @TODO - Partial security audit
// @TODO - timestamps / block numbers?  justify rationale for choice
// @TODO - ERC20 warning

pragma solidity ^0.4.0;

contract ParalysisProof {

    // Instance-specific parameters
    uint256 public delta;
    uint256 public mu1;     // mu = mu1 / mu2, for a 'mu1 of mu2 allowed multisig'
    uint256 public mu2;
    address[] public keyholders;

    // Paralysis claims and confirmed paralyzed users
    struct ParalysisClaim {
        uint256 expiry;
        bool responded;
    }
    mapping(address=>ParalysisClaim) paralysis_claims;
    mapping(address=>bool) paralyzed;
    event NewAccusation(address accused, uint256 respond_by);

    // Spend proposals and their signatures / approvals
    struct SpendProposal {
        address to;
        uint256 amount;
        bool filled;
    }
    SpendProposal[] proposals;
    mapping (uint256 => mapping (address => bool)) proposal_sigs;

    // Modifier ensuring that expensive/necessary updates to remove paralyzed keyholders are only performed once per transaction
    // (this pruning is necessary, as a timeout for response may have elapsed since the last transaction, paralyzing a keyholder)
    // IMPORTANT: Any method which requires up to date data on which keyholders are paralyzed should carry this modifier
    bool upToDate = false;
    modifier updateRequired {
        if (!upToDate) {
            prune_paralyzed_keyholders();
            upToDate = true;
            _;
            upToDate = false;
        }
        else {
            _;
        }
    }

    uint256 num_responsive; // Number of users alive to respond to claims; only meaningful with upToDate = true; do not access directly!!
    function num_responsive_keys() public updateRequired returns(uint256) {
        return num_responsive;
    }

    // If any keyholders have become paralyzed since last tx, updates their status appropriately
    function prune_paralyzed_keyholders() internal {
        uint256 nparalyzed = 0;
        for (uint256 i = 0; i < keyholders.length; i++) {
            if (!paralyzed[keyholders[i]]) {
                uint256 expiry = paralysis_claims[keyholders[i]].expiry;
                if (expiry < now && expiry > 0) {
                    if (!paralysis_claims[keyholders[i]].responded) {
                        // active claim, unresponded.  set paralyzed
                        paralyzed[keyholders[i]] = true;
                        nparalyzed++;
                    }
                }
            }
            else {
                nparalyzed++;
            }
        }
        num_responsive = (keyholders.length - nparalyzed);
    }

    function ParalysisProof(uint256 _mu1, uint256 _mu2, uint256 _delta, address[] _keyholders) public {
        require(_mu1 <= _mu2);            // at most 100% of keyholders required
        require(_mu2 != 0);               // no such thing as an -of-0 multisig
        require(_keyholders.length > 0);  // to prevent stuck $, at least 1 keyholder required
        require(_keyholders.length < 20); // to establish gas upper bounds
        require(_delta > 2 hours);        // to guard against temporary DoS (tune as desired)
        require(_delta < 4 weeks);        // to guard against stuck money   (tune as desired)
        mu1 = _mu1;
        mu2 = _mu2;
        delta = _delta;
        keyholders = _keyholders;
    }

    function() payable {} // allow money in

    // Return true if user is an active(unparalyzed) keyholder, false otherwise
    function is_active_keyholder(address holder) public updateRequired returns(bool) {
        for (uint256 i = 0; i < keyholders.length; i++) {
            if (keyholders[i] == holder)
                return !paralyzed[holder];
        }
        return false;
    }

    // Create a standard multisig-style proposal to spend funds
    function createSpendProposal(address to, uint256 amount) public updateRequired returns(uint256) {
        require(is_active_keyholder(msg.sender));
        uint256 proposal_id = proposals.length;
        proposals.push(SpendProposal(to, amount, false));
        proposal_sigs[proposal_id][msg.sender] = true;    // consider any submitted proposal signed by its sender
        return proposal_id;
    }

    // Approve a proposal and execute if signature threshold is reached
    function spend(uint256 proposal_id) public updateRequired {
        require(is_active_keyholder(msg.sender));
        require(proposal_id < proposals.length);

        // add sender's signature to approval
        proposal_sigs[proposal_id][msg.sender] = true;

        // if enough proposers approved, send money
        uint256 num_signatures = 0;
        for (uint256 i = 0; i < keyholders.length; i++) {
            if (!paralyzed[keyholders[i]]) {
                if (proposal_sigs[proposal_id][keyholders[i]]) {
                    num_signatures++;
                }
            }
        }

        if (((num_signatures) * mu2) >= (num_responsive_keys() * mu1)) {
            if (!proposals[proposal_id].filled) {
                proposals[proposal_id].filled = true;
                proposals[proposal_id].to.transfer(proposals[proposal_id].amount);
            }
        }
    }

    // Accuse a user of being paralyzed
    function accuse(address accused) public updateRequired returns(uint256) {
        address accuser = msg.sender;

        // users cannot accuse themselves (ensures always at least one active keyholder; prevent stuck funds)
        require(accuser != accused);

        // both requester and accused must be active keyholders
        require(is_active_keyholder(accuser));
        require(is_active_keyholder(accused));

        // there shouldn't be any outstanding claims against accused
        require(!(paralysis_claims[accused].expiry >= now));

        // create and insert an Paralysis Claim
        uint256 expiry = now+delta;
        paralysis_claims[accused] = ParalysisClaim(expiry, false);
        NewAccusation(accused, expiry); // notify the accused
        return expiry;
    }

    // Respond to a claim of paralysis with a life signal
    function respond() public {
        // IMPORTANT: Check that accusation is mined/sufficiently confirmed before responding to avoid front-running attacks
        require(paralysis_claims[msg.sender].expiry >= now); // requires active pending claim (implicitly checks for being keyholder)
        paralysis_claims[msg.sender].responded = true;      // sets status of claim as responded to, keeps user alive
    }
}
