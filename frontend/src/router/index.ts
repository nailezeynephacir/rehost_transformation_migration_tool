import { createRouter, createWebHistory } from "vue-router";
import ExtractView from "../views/ExtractView.vue";
import ApplyView from "../views/ApplyView.vue";
import StoryView from "../views/StoryView.vue";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/extract" }, // Extract is the default mode, decided Wednesday
    { path: "/extract", component: ExtractView, name: "extract" },
    { path: "/apply", component: ApplyView, name: "apply" },
    { path: "/story", component: StoryView, name: "story" },
  ],
});

export default router;