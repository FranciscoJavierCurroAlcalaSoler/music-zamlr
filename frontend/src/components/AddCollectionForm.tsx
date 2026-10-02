import { useState, type FormEvent } from "react";
import { Box, Button, Stack, TextField } from "@mui/material";
import { open } from "@tauri-apps/plugin-dialog";

import { isDesktop } from "../connection";

interface AddCollectionFormProps {
  disabled: boolean;
  loading: boolean;
  onCreate: (name: string, rootPath: string) => Promise<boolean>;
}

export function AddCollectionForm({
  disabled,
  loading,
  onCreate,
}: AddCollectionFormProps) {
  const [name, setName] = useState("");
  const [rootPath, setRootPath] = useState("");

  async function handleBrowse() {
    const picked = await open({
      directory: true,
      multiple: false,
      title: "Choose the collection folder",
    });
    // Anything that is not a string means the dialog was cancelled, and a
    // cancel must leave a path the user typed exactly where it was.
    if (typeof picked === "string") {
      setRootPath(picked);
    }
  }

  // A real <form>, so Enter in either field submits. preventDefault stops the
  // browser's own navigating submit; the button's disabled state still gates
  // Enter, because implicit submission activates the submit button and a
  // disabled one does nothing.
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const success = await onCreate(name, rootPath);
    if (success) {
      setName("");
      setRootPath("");
    }
  }

  return (
    <Box component="form" onSubmit={handleSubmit}>
      <Stack spacing={2}>
        <TextField
          label="Collection name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          fullWidth
        />
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <TextField
            label="Folder path"
            value={rootPath}
            onChange={(e) => setRootPath(e.target.value)}
            placeholder="D:\Music"
            fullWidth
          />
          {/* Only in the desktop app. A native dialog in a browser would
              pick a folder on whichever machine the browser runs, which is
              not the machine the backend reads from. The field stays, since
              typing or pasting a path is the only way there — and the
              faster way for a path already in hand. */}
          {isDesktop() && (
            <Button variant="outlined" onClick={handleBrowse}>
              Browse…
            </Button>
          )}
        </Stack>
        <Button
          type="submit"
          variant="contained"
          disabled={
            disabled || loading || name.trim() === "" || rootPath.trim() === ""
          }
        >
          {loading ? "Creating..." : "Create collection"}
        </Button>
      </Stack>
    </Box>
  );
}
