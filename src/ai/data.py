import pandas as pd
import json
from typing import List, Tuple

# All numeric features that can be used for ML model training
# These come directly from the radio_stats table
ML_FEATURE_COLUMNS = [
    'channel_utilization_pct',
    'tx_airtime_pct',
    'rx_airtime_pct',
    'cca_busy_pct',
    'noise_floor_dbm',
    'client_count',
    'active_client_count',
    'avg_rssi_dbm',
    'min_rssi_dbm',
    'avg_snr_db',
    'min_snr_db',
    'avg_tx_rate_mbps',
    'avg_rx_rate_mbps',
    'tx_retries',
    'tx_failed',
    'tx_airtime_client_pct',
    'rx_airtime_client_pct',
    'avg_mcs',
    'min_mcs',
    'avg_nss',
    'weak_client_count',
    'neighbor_ap_count',
    'strong_neighbor_ap_count',
    'same_channel_ap_count',
    'strong_same_channel_ap_count',
    'obss_utilization_pct',
    'interference_utilization_pct',
    'bandwidth_mhz',
    'channel',
    'frequency_mhz',
]

def load_json_training_data(json_path: str) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Load training data from JSON file with labels.
    
    JSON format:
    {
      "rows": [
        {
          "timestamp": "...",
          "device_id": "...",
          ...all db columns...,
          "label": 0 or 1
        },
        ...
      ]
    }
    
    Args:
        json_path: Path to JSON training file
        
    Returns:
        Tuple of (features_df, labels_series)
    """
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    rows = data.get('rows', [])
    if not rows:
        raise ValueError(f"No rows found in JSON file: {json_path}")
    
    df = pd.DataFrame(rows)
    
    # Extract labels
    if 'label' not in df.columns:
        raise ValueError("JSON data must include 'label' column (0=healthy, 1=anomaly)")
    
    labels = df['label'].copy()
    
    # Remove non-feature columns
    exclude_cols = {'label', 'timestamp', 'scenario', 'schema_version', 'network_type', 'ifname'}
    feature_cols = [col for col in df.columns if col not in exclude_cols]
    
    features_df = df[feature_cols].copy()
    
    return features_df, labels


def load_csv_training_data(csv_path: str) -> pd.DataFrame:
    """
    Load training data from CSV file.
    
    Args:
        csv_path: Path to CSV training file
        
    Returns:
        DataFrame with telemetry data
    """
    df = pd.read_csv(csv_path)
    df['timestamp'] = pd.to_datetime(df.get('timestamp', df.get('ts', None)))
    return df


def prepare_ml_features(df: pd.DataFrame, feature_columns: List[str] = None) -> pd.DataFrame:
    """
    Prepare ML features from radio_stats rows.
    
    Selects numeric columns, handles missing values, and ensures consistency.
    
    Args:
        df: DataFrame with radio_stats data
        feature_columns: List of feature columns to use (defaults to ML_FEATURE_COLUMNS)
        
    Returns:
        DataFrame with prepared features
    """
    if feature_columns is None:
        feature_columns = ML_FEATURE_COLUMNS
    
    # Select only available columns
    available_cols = [col for col in feature_columns if col in df.columns]
    
    X = df[available_cols].copy()
    
    # Fill missing values with 0
    X = X.fillna(0)
    
    # Ensure all numeric
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors='coerce').fillna(0)
    
    return X, available_cols
