import {
  Alert,
  Box,
  Button,
  Table,
  TableBody,
  TableContainer,
  TableRow,
  TableHead,
  TableCell,
  CircularProgress,
} from "@mui/material";
import type { Collection, ScanProgress, ScanResult } from "../types";
import { formatTimestamp } from "../format";
import { useState } from "react";
import {
  rescanCollection,
  describeFetchError,
  createCollection,
  deleteCollection,
} from "../api";
import { ScanResultView } from "./ScanResultView";
import { ScanProgressView } from "./ScanProgressView";
import { AddCollectionForm } from "./AddCollectionForm";
import { RemoveCollectionDialog } from "./RemoveCollectionDialog";

interface CollectionsViewProps {
  collections: Collection[];
  loadingCollections: boolean;
  onScanned: () => Promise<void>;
  operationRunning: boolean;
}

export function CollectionsView({
  collections,
  loadingCollections,
  onScanned,
  operationRunning,
}: CollectionsViewProps) {
  const [scanningId, setScanningId] = useState<number | null>(null);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [progress, setProgress] = useState<ScanProgress | null>(null);
  // The target stays set after the dialog closes, so the dialog keeps its text
  // while it fades out. The next Remove overwrites it.
  const [removeTarget, setRemoveTarget] = useState<Collection | null>(null);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [removing, setRemoving] = useState(false);

  async function runRescan(id: number) {
    setScanningId(id);
    setScanResult(null);
    setScanError(null);

    try {
      const result: ScanResult = await rescanCollection(id, setProgress);
      // On success only, unlike runCreate. scan_folder commits once at the
      // very end, so a re-scan that failed left nothing new for the list to
      // show. runCreate refreshes either way, because there the collection
      // row is written before the scan starts and outlives its failure.
      await onScanned();
      setScanResult(result);
    } catch (error: unknown) {
      setScanError(describeFetchError(error));
    } finally {
      setScanningId(null);
      setProgress(null);
    }
  }

  async function runCreate(name: string, rootPath: string) {
    setCreating(true);
    setScanResult(null);
    setScanError(null);

    try {
      const result: ScanResult = await createCollection(
        name,
        rootPath,
        setProgress,
      );
      setScanResult(result);
      return true;
    } catch (error: unknown) {
      setScanError(describeFetchError(error));
      return false;
    } finally {
      // Even after a failure. The backend writes the collection row before
      // the scan begins, so a scan that dies partway leaves a real row that
      // the list would otherwise never show — and creating it again then
      // fails with "already exists". Awaiting inside finally is fine: it
      // completes before the promise settles, so AddCollectionForm clears
      // its fields only once the refreshed list has arrived.
      await onScanned();
      setCreating(false);
      setProgress(null);
    }
  }

  async function runRemove() {
    if (removeTarget === null) return;

    setRemoving(true);
    setScanError(null);
    setScanResult(null);
    try {
      await deleteCollection(removeTarget.id);
    } catch (error: unknown) {
      setScanError(describeFetchError(error));
    } finally {
      // After a failure too, as in runCreate: the list must show what the
      // server holds, whichever way the request ended.
      await onScanned();
      setRemoving(false);
      setRemoveOpen(false);
    }
  }

  const busy = scanningId !== null || creating || removing;

  return (
    <Box>
      <AddCollectionForm
        disabled={busy}
        loading={creating}
        onCreate={runCreate}
      />
      <TableContainer>
        <Table>
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Root path</TableCell>
              <TableCell>Last scanned</TableCell>
              <TableCell></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loadingCollections ? (
              <TableRow>
                <TableCell colSpan={4}>
                  <CircularProgress />
                </TableCell>
              </TableRow>
            ) : collections.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4}>No collections found.</TableCell>
              </TableRow>
            ) : (
              collections.map((collection) => (
                <TableRow key={collection.id}>
                  <TableCell>{collection.name}</TableCell>
                  <TableCell>{collection.root_path}</TableCell>
                  <TableCell>
                    {formatTimestamp(collection.last_scanned_at)}
                  </TableCell>
                  <TableCell>
                    <Button
                      onClick={() => runRescan(collection.id)}
                      disabled={busy}
                    >
                      {scanningId === collection.id ? "Scanning..." : "Scan"}
                    </Button>
                    <Button
                      color="error"
                      onClick={() => {
                        setRemoveTarget(collection);
                        setRemoveOpen(true);
                      }}
                      disabled={busy || operationRunning}
                    >
                      Remove
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {scanError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {scanError}
        </Alert>
      )}

      <ScanProgressView progress={progress} />
      <ScanResultView
        result={scanResult}
        onDismiss={() => setScanResult(null)}
      />
      <RemoveCollectionDialog
        open={removeOpen}
        collection={removeTarget}
        removing={removing}
        onCancel={() => setRemoveOpen(false)}
        onConfirm={runRemove}
      />
    </Box>
  );
}
