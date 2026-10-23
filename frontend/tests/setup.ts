import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// The application workspace renders many panels at once; under parallel test load the first paint can exceed
// Testing Library's 1 s default for findBy*/waitFor. Assertions are unchanged — only the wait budget grows.
configure({ asyncUtilTimeout: 4000 });

afterEach(() => {
  cleanup();
});
