import { defineStore } from "pinia";
import { ref } from "vue";
import {
    listWorldviewCollections,
    createWorldviewCollection,
    updateWorldviewCollection,
    deleteWorldviewCollection
} from "../api/worldviewCollection.js";
import {
    listWorldviewEntriesByCollection,
    createWorldviewEntry,
    updateWorldviewEntry,
    deleteWorldviewEntry
} from "../api/worldviewEntry.js";

export const useWorldviewStore = defineStore("worldview", () => {
    const collections = ref([]);
    const entriesMap = ref({});
    const loading = ref(false);

    async function load() {
        loading.value = true;
        try {
            collections.value = (await listWorldviewCollections()) || [];
        } finally {
            loading.value = false;
        }
    }

    async function loadEntries(collectionId) {
        const entries = (await listWorldviewEntriesByCollection(collectionId)) || [];
        entriesMap.value[collectionId] = entries;
        return entries;
    }

    async function createCollection(data) {
        const col = await createWorldviewCollection(data);
        collections.value.push(col);
        return col;
    }

    async function updateCollection(id, data) {
        await updateWorldviewCollection(id, data);
        const idx = collections.value.findIndex((c) => c.worldviewCollectionID === id);
        if (idx !== -1) Object.assign(collections.value[idx], data);
    }

    async function removeCollection(id) {
        await deleteWorldviewCollection(id);
        collections.value = collections.value.filter((c) => c.worldviewCollectionID !== id);
        delete entriesMap.value[id];
    }

    async function createEntry(data) {
        const entry = await createWorldviewEntry(data);
        const pid = data.parentID || entry.parentID;
        if (!entriesMap.value[pid]) entriesMap.value[pid] = [];
        entriesMap.value[pid].push(entry);
        return entry;
    }

    async function updateEntry(id, data, parentId) {
        await updateWorldviewEntry(id, data);
        if (parentId && entriesMap.value[parentId]) {
            const idx = entriesMap.value[parentId].findIndex((e) => e.worldviewCollectionEntryID === id);
            if (idx !== -1) Object.assign(entriesMap.value[parentId][idx], data);
        }
    }

    async function removeEntry(id, parentId) {
        await deleteWorldviewEntry(id);
        if (parentId && entriesMap.value[parentId]) {
            entriesMap.value[parentId] = entriesMap.value[parentId].filter((e) => e.worldviewCollectionEntryID !== id);
        }
    }

    return {
        collections,
        entriesMap,
        loading,
        load,
        loadEntries,
        createCollection,
        updateCollection,
        removeCollection,
        createEntry,
        updateEntry,
        removeEntry
    };
});
