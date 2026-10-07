-- PostGIS (geography types, spatial joins) and pgvector (image embeddings), see SPEC §5.3.
create extension if not exists postgis with schema extensions;
create extension if not exists vector with schema extensions;
