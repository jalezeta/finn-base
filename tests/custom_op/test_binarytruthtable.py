# Copyright (c) 2021 Xilinx, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of Xilinx nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import numpy as np
import onnx.helper as helper
from onnx import TensorProto

import finn.core.onnx_exec as oxe
from finn.core.datatype import DataType
from finn.core.modelwrapper import ModelWrapper
from finn.custom_op.registry import getCustomOp
from finn.transformation.infer_datatypes import InferDataTypes
from finn.transformation.infer_shapes import InferShapes
from finn.transformation.logicnets.gen_bintruthtable_verilog import (
    GenBinaryTruthTableVerilog,
)

export_onnx_path = "test_truthtable.onnx"


def test_binarytruthtable():

    # Tensor with different input combinations
    input_data_vector = np.array(
        [
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 1],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 1, 1, 0, 0, 1],
            [0, 0, 0, 0, 0, 0, 1, 0, 1, 0, 1, 1, 0, 1, 1, 1],
            [0, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1],
        ],
        dtype=np.float32,
    )
    # Set the care set
    care_set_data = np.asarray([1, 58, 15, 89, 695, 6485], dtype=np.float32)
    in_bits = 16

    # Set input and care_set tensor information
    inputs = helper.make_tensor_value_info("inputs", TensorProto.FLOAT, [in_bits])
    care_set = helper.make_tensor_value_info(
        "care_set", TensorProto.FLOAT, [care_set_data.size]
    )
    output = helper.make_tensor_value_info("output", TensorProto.FLOAT, [1])
    # Define the custom node with "python" mode
    node_def = helper.make_node(
        "BinaryTruthTable",
        ["inputs", "care_set"],
        ["output"],
        domain="finn.custom_op.general",
        in_bits=in_bits,
        exec_mode="python",
    )
    # Create the graph and the model
    modelproto = helper.make_model(
        helper.make_graph([node_def], "test_model", [inputs, care_set], [output])
    )
    # Wrap the model for finn and set the input tensor datatypes as desired
    model = ModelWrapper(modelproto)
    model.set_tensor_datatype("inputs", DataType.BINARY)
    model.set_tensor_datatype("care_set", DataType.UINT32)

    # test output shape
    model = model.transform(InferShapes())
    assert model.get_tensor_shape("output") == [1]
    # test output type
    assert model.get_tensor_datatype("output") is DataType.FLOAT32
    model = model.transform(InferDataTypes())
    assert model.get_tensor_datatype("output") is DataType.BINARY
    # Loop over "python" and "rtlsim" execution modes
    for x in range(2):
        # Loop over different input combinations
        for input_data in input_data_vector:
            # Create input dictionary
            in_dict = {
                "inputs": input_data,
                "care_set": care_set_data,
            }
            # Perform execution
            out_dict = oxe.execute_onnx(model, in_dict)
            # Calculate result here locally for comparison with the CustomOp result
            input_data = input_data[::-1]
            out_idx = 0
            for idx, val in enumerate(input_data):
                out_idx += (1 << idx) * val
            entry = 1 if out_idx in care_set_data else 0
            # compare outputs
            assert entry == out_dict["output"]
        # Change execution mode into "rtlsim" for simulation with PyVerilator
        myOp = getCustomOp(model.graph.node[0])
        myOp.set_nodeattr("exec_mode", "rtlsim")

    # test transformation to generate verilog
    model = model.transform(
        GenBinaryTruthTableVerilog(num_workers=None, care_set=care_set_data)
    )