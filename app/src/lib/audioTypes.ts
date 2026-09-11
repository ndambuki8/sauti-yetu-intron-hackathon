export type Clip = {
  uri: string;
  filename: string;
  mime: string;
  blob?: Blob;
};

export type RecordingHandle = {
  stop: () => Promise<Clip>;
};
