import js from "@eslint/js";

export default [
    js.configs.recommended,
    {
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: "module",
            globals: { window: "readonly", document: "readonly", localStorage: "readonly", indexedDB: "readonly", fetch: "readonly", setTimeout: "readonly", setInterval: "readonly", clearInterval: "readonly", console: "readonly" },
        },
        ignores: ["dist", "node_modules", "coverage"],
        rules: { "no-unused-vars": "warn" },
    },
];
