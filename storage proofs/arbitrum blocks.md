Arbitrum block number and block hashes
--------------------------------------

Our storage proofs depend on the input of an agreed upon random challenge. We
use ethereum block hashes as the source of randomness. The [timing of storage
proofs][1] is also dependent on the same randomness.

Due to [intricacies of the EVM][2], it is important for our design to know the
cadence at which the block number increases, and whether the view of the latest
256 block hashes that are available in the EVM match this cadence.

L2 rollups such as Arbitrum complicate this further, because there are two types
of block numbers (L1 and L2), and two types of block hashes (L1 and L2).

Because the Arbiturm documentation seems to have [conflicting][3]
[information][4] about where the block hashes that are returned by `blockhash()`
come from, we performed an experiment to figure this out. We deployed a contract
that exposes the `block.number` and the 256 block hashes on the arbitrum
testnet. The code for this experiment can be found in the [evm-block-info][5]
repo.

Outcomes from this experiment:
- `block.number` increases roughly every 12 seconds, and it matches the block
  number of the L1 block chain (Sepolia)
- `blockhash()` returns L2 block hashes, but the cadence at which these block
  hashes move through the 256 block window matches the 12 second block time. In
  contrast to an L1 EVM, two adjacent blockhashes do not represent blocks that
  have a parent-child relationship because there are many blocks between them.

Conclusions:
- Block hashes from the Arbitrum L2 are a weaker source of randomness than the
  block hashes from the L1. This should probably not come as a surprise because
  the Arbitrum sequencer is centralized and can therefore easily influence the
  block hash.
- Unfortunately there is currently no [access to L1 block hashes][6] in the EVM
  on Arbitrum
- Block cadence and the cadence at which block hashes become available matches
  that of the L1, and is therefore compatible with our [proof timing][7] design.

[1]: https://github.com/durability-labs/archivist-research-old/blob/master/design/storage-proof-timing.md
[2]: https://github.com/durability-labs/archivist-research-old/blob/master/design/storage-proof-timing.md#evm-and-solidity
[3]: https://docs.arbitrum.io/build-decentralized-apps/arbitrum-vs-ethereum/solidity-support
[4]: https://docs.arbitrum.io/how-arbitrum-works/deep-dives/geth#l1blockhash
[5]: https://github.com/durability-labs/evm-block-info
[6]: https://research.arbitrum.io/t/access-to-l1-block-hash-on-arbitrum/9635
[7]: https://github.com/durability-labs/archivist-research-old/blob/master/design/storage-proof-timing.md#block-pointers