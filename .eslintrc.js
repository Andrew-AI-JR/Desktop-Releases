module.exports = {
  env: {
    browser: true,
    commonjs: true,
    es2021: true,
    node: true,
  },
  extends: ['eslint:recommended'],
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  overrides: [
    {
      files: ['src/main/**/*.js', 'src/services/**/*.js', 'scripts/**/*.js'],
      parserOptions: {
        sourceType: 'commonjs',
      },
    },
    {
      files: ['src/renderer/**/*.js'],
      parserOptions: {
        sourceType: 'module',
      },
    },
  ],
  rules: {
    'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    'no-console': 'off',
    semi: ['error', 'always'],
    quotes: ['error', 'single'],
  },
  ignorePatterns: [
    'dist/',
    'build/',
    'resources/python-executables/',
    'node_modules/',
    '*.log',
  ],
};
