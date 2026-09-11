import { Redirect } from "expo-router";
import { useWindowDimensions } from "react-native";
import { RecordSession } from "../../components/RecordSession";

export default function SessionRecordScreen() {
  const wide = useWindowDimensions().width >= 900;
  if (wide) return <Redirect href="/session/graph" />;
  return <RecordSession />;
}
