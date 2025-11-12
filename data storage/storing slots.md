Storing slots from the marketplace
----------------------------------

This design describes the interaction between the sales module and the repo
store. The sales module identifies opportunities for earning tokens by looking
for new storage requests and older storage requests in need of repair. Once the
sales module finds a profitable storage request on the [marketplace][1], it
instructs the repo store to download and store a slot from that request.

This document improves on the [older design][2] by simplifying the concept of
available storage (multiple availabilities are removed), and removing
intermediate state that could get out of sync with reality.

[1]: https://github.com/durability-labs/archivist-research-old/blob/master/design/marketplace.md
[2]: https://github.com/durability-labs/archivist-research-old/blob/master/design/sales.md

### Overview ###

```
  --------------
  |    Sales   |
  --------------
        |
        |
        v
  --------------
  | Slot Store |
  --------------
        |
        |
        v
  --------------
  | Repo Store |
  --------------
```

We identify the following concerns that the node needs to address:

1. *quota*: ensure that the stored slots together do not exceed a certain amount
   of disk space as specified by the node operator
2. *expiration*: ensure that slots that no longer need to be stored are removed
   from disk
3. *duplicates*: ensure that contract renewal, and other situations where
   different slots reference the same data, are handled correctly
4. *interleaving*: ensure that long running operations such as downloading or
   deleting a slot, either succeed or can be retried, even when download
   and deletion of the same data is requested simultanuously.

Expiration (2) and duplicates (3) will be handled by the slot store, a component
that sits between the sales module and the repo store. Interleaving (4) will be
handled by the repo store. Quota (1) will be handled in part by the slot store
and in part by the repo store.

### Slot Store ###

```nim
SlotStore.quota
SlotStore.quotaUsed
SlotStore.updateQuota(quota)
SlotStore.storeSlot(slotId, manifestCid, slotIndex, expiry)
SlotStore.updateExpiry(slotId, expiry)
```

The slot store keeps a list of all stored slots, when they expire, and how much
space they take up. This list is persisted in a metadata store. It is the
responsibility of the slot store to ensure that updates to the list of stored
slots and their quota use happen atomically.

The sales module calls `SlotStore.storeSlot()` when it wants to store a slot
from a storage request. The slot store checks that the slot fits into the quota.
It then adds the slot to the list of slots and makes sure that the updated list
is persisted. Then it asks the repo store to download the slot data by invoking
`RepoStore.storeSlot()`.


The sales module can ask the slot store to update the expiry timestamp of a slot
through `updateExpiry()`. If the new expiry timestamp is in the past,
then that signals that the slot can be removed from the repo store.

The slot store runs a continuous process that checks for expired slots. When a
slot expires, it can be removed from the slot store. If no other slot references
the same `manifestCid` and `slotIndex`, then the slot data can also be removed
from the repo store by calling `RepoStore.removeSlot()`.

The `SlotStore.quotaUsed` property reflects the full size of all stored slots
combined, irrespective of how much of these slots is stored on disk. This allows
the sales module to determine how much space is still available for new slots.
This means that `SlotStore.quotaUsed` is always larger than or equal to the
`RepoStore.slotQuotaUsed` property, because the latter reflects how much data is
actually stored on disk.

The sales module can ask the slot store to change the slot quota by calling
`SlotStore.updateQuota()`. This typically happens when a node operator wants to
change the amount of storage that they want to sell. The slot store should check
that the new quota is not smaller than `SlotStore.quotaUsed`, and then call
`RepoStore.updateSlotQuota()`.

### Repo Store ###

```nim
RepoStore.slotQuota
RepoStore.slotQuotaUsed
RepoStore.updateSlotQuota(quota)
RepoStore.storeSlot(manifest, slotIndex)
RepoStore.removeSlot(manifest, slotIndex)
```

A call to `RepoStore.updateSlotQuota()` should fail when increasing the slot
quota would exceed the overall quota of the repo store. It should also fail when
the new quota is less than `RepoStore.slotQuotaUsed`. The
`RepoStore.slotQuotaUsed` property reflects the combined size of all slot blocks
that are stored on disk.

When asked to store a slot through `storeSlot()`, the repo store should download
and store the slot data. The slot data and the manifest should be kept until
`removeSlot()` is called. 

Both `storeSlot()` and `removeSlot()` are async functions that complete when the
entire slot has been stored/removed. Both functions should be resilient when
invoked multiple times for the same slot. They should complete succesfully when
the slot was already stored/removed before. When there are simultanous calls to
`storeSlot()` and `removeSlot()` for the same slot then at least one of the
operations should fail.
