import { defineStore } from "pinia";
import { ref } from "vue";
import {
    listUserCharacters,
    createUserCharacter,
    updateUserCharacter,
    deleteUserCharacter
} from "../api/userCharacter.js";

export const useUserCharacterStore = defineStore("userCharacter", () => {
    const cards = ref([]);
    const loading = ref(false);

    async function load() {
        loading.value = true;
        try {
            cards.value = (await listUserCharacters()) || [];
        } finally {
            loading.value = false;
        }
    }

    async function create(data) {
        const card = await createUserCharacter(data);
        cards.value.push(card);
        return card;
    }

    async function update(id, data) {
        await updateUserCharacter(id, data);
        const idx = cards.value.findIndex((c) => c.userCharacterID === id);
        if (idx !== -1) Object.assign(cards.value[idx], data);
    }

    async function remove(id) {
        await deleteUserCharacter(id);
        cards.value = cards.value.filter((c) => c.userCharacterID !== id);
        try { await load(); } catch {}
    }

    return { cards, loading, load, create, update, remove };
});
