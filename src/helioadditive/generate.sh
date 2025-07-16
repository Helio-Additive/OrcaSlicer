#!/bin/bash

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd $SCRIPT_DIR

$SCRIPT_DIR/../../deps/build_arm64/dep_cppgraphqlgen-prefix/src/dep_cppgraphqlgen-build/src/clientgen \
    --schema ./schema.graphqls \
    --request ./queries/ListMaterials.graphql \
    --namespace HelioAdditive \
    --prefix ListMaterials \
    --source-dir ./src \
    --header-dir ./include
