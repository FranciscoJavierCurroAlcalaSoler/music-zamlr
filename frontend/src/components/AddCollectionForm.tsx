import { useState, type FormEvent } from "react";
import { Box, Button, Stack, TextField } from "@mui/material";

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
        <TextField
          label="Folder path"
          value={rootPath}
          onChange={(e) => setRootPath(e.target.value)}
          placeholder="D:\Music"
          fullWidth
        />
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
