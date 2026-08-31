import { defineStore } from "pinia";
import { ref } from "vue";
import {
    listCharacterCards,
    createCharacterCard,
    updateCharacterCard,
    deleteCharacterCard
} from "../api/characterCard.js";

export const useCharacterStore = defineStore("character", () => {
    const cards = ref([]);
    const loading = ref(false);

    async function load() {
        loading.value = true;
        try {
            cards.value = (await listCharacterCards()) || [];
        } finally {
            loading.value = false;
        }
    }

    async function create(data) {
        const card = await createCharacterCard(data);
        cards.value.push(card);
        return card;
    }

    async function update(id, data) {
        await updateCharacterCard(id, data);
        try { await load(); } catch {}
    }

    async function remove(id) {
        await deleteCharacterCard(id);
        cards.value = cards.value.filter((c) => c.characterID !== id);
        try { await load(); } catch {}
    }

    return { cards, loading, load, create, update, remove };
});
